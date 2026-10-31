// Opt-in sandbox scratch probe. No account, model, installer or policy changes.
// It must run only on an isolated disposable Windows machine after review.
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Atlas.NativeApprovalDev;

internal static class NativeSandboxProbe
{
    internal static string RedactScratch(string message, string scratch) => message.Replace(scratch.Replace("\\", "\\\\"), "<scratch>", StringComparison.OrdinalIgnoreCase).Replace(scratch, "<scratch>", StringComparison.OrdinalIgnoreCase);
    private static async Task DrainBounded(Stream stream, CancellationToken stop)
    {
        var buffer = new byte[4096]; int count = 0, n;
        while ((n = await stream.ReadAsync(buffer.AsMemory(), stop)) != 0)
            if ((count += n) > 1_048_576) throw new InvalidDataException("Probe output exceeded the bound.");
    }
    // Also used by a fake-child fixture; this function cannot launch the real
    // CLI without an explicit ProcessStartInfo supplied by its trusted caller.
    internal static async Task VerifyContainedAsync(ProcessStartInfo info, string inside, string outside, CancellationToken stop)
    {
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(stop); limit.CancelAfter(TimeSpan.FromSeconds(30));
        using var child = ContainedProviderProcess.Start(info);
        var drain = DrainBounded(child.Output, limit.Token);
        await child.Process.WaitForExitAsync(limit.Token);
        await drain.WaitAsync(limit.Token);
        if (child.Process.ExitCode != 0 || !File.Exists(inside) || File.Exists(outside)) throw new InvalidOperationException("Scratch sandbox write-boundary probe did not pass.");
    }
    internal static async Task<string> RunCaptureAsync(ProcessStartInfo info, CancellationToken stop, bool mergeErrorWithOutput = false)
    {
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(stop); limit.CancelAfter(TimeSpan.FromSeconds(45));
        using var child = ContainedProviderProcess.Start(info, mergeErrorWithOutput: mergeErrorWithOutput);
        using var bytes = new MemoryStream();
        async Task Capture()
        {
            byte[] buffer = new byte[1024]; int n;
            while ((n = await child.Output.ReadAsync(buffer.AsMemory(), limit.Token)) != 0)
            {
                if (bytes.Length + n > 8192) throw new InvalidDataException("Probe output exceeded the bound.");
                bytes.Write(buffer, 0, n);
            }
        }
        var output = Capture();
        await child.Process.WaitForExitAsync(limit.Token);
        await output.WaitAsync(limit.Token);
        string message = Encoding.UTF8.GetString(bytes.ToArray());
        message = new string(message.Select(c => char.IsControl(c) ? ' ' : c).ToArray());
        if (child.Process.ExitCode != 0) throw new InvalidOperationException("Contained MXC probe failed (exit " + child.Process.ExitCode + "): " + message);
        return message;
    }
    // Builds only scratch files and a process description; no process is run.
    internal static ProcessStartInfo BuildProbeStart(string executable, string scratch, int listenerPort)
    {
        if (listenerPort < 1 || listenerPort > 65535 || !Path.IsPathFullyQualified(scratch)) throw new InvalidOperationException("Valid isolated probe inputs are required.");
        if (scratch.Any(c => c > 127) || scratch.IndexOfAny(new[] { '%', '!', '&', '|', '<', '>', '^', '\r', '\n' }) >= 0) throw new InvalidOperationException("Unsafe scratch path for command interpreter.");
        string project = Path.Combine(scratch, "project"), outside = Path.Combine(scratch, "outside"), profile = Path.Combine(scratch, "profile"), temp = Path.Combine(scratch, "runtime-temp");
        Directory.CreateDirectory(project); Directory.CreateDirectory(outside); Directory.CreateDirectory(temp); Directory.CreateDirectory(Path.Combine(profile, "appdata")); Directory.CreateDirectory(Path.Combine(profile, "local")); Directory.CreateDirectory(Path.Combine(profile, ".codex"));
        string outsideFile = Path.Combine(outside, "must-not-be-written.txt"), script = Path.Combine(project, "fixture.cmd");
        string system = Environment.SystemDirectory, windows = Directory.GetParent(system)?.FullName ?? throw new InvalidOperationException("Windows directory unavailable.");
        string powershell = Path.Combine(system, "WindowsPowerShell", "v1.0", "powershell.exe");
        string network = "$ErrorActionPreference='Stop'; try { $c=New-Object System.Net.Sockets.TcpClient; $a=$c.BeginConnect('127.0.0.1'," + listenerPort + ",$null,$null); if (-not $a.AsyncWaitHandle.WaitOne(2000)) { exit 31 }; $c.EndConnect($a); exit 32 } catch { if ($_.Exception -is [System.Net.Sockets.SocketException] -or $_.Exception.InnerException -is [System.Net.Sockets.SocketException]) { exit 31 }; exit 33 }";
        // Stable markers identify which scratch-only check ran without
        // printing paths or other environment values in CI diagnostics.
        string scriptText = "@echo off\r\necho ATLAS_PROBE_STARTED\r\necho inside>\"%~dp0inside.txt\"\r\nif errorlevel 1 (echo ATLAS_INSIDE_DENIED & exit /b 11)\r\necho ATLAS_INSIDE_WRITTEN\r\necho outside>\"" + outsideFile + "\"\r\nif not errorlevel 1 (echo ATLAS_OUTSIDE_WRITTEN & exit /b 12)\r\necho ATLAS_OUTSIDE_DENIED\r\n" +
            "\"" + powershell + "\" -NoProfile -NonInteractive -Command \"exit 0\"\r\nif errorlevel 1 (echo ATLAS_POWERSHELL_FAILED & exit /b 13)\r\necho ATLAS_POWERSHELL_READY\r\n" +
            "\"" + powershell + "\" -NoProfile -NonInteractive -Command \"" + network + "\"\r\nif errorlevel 33 (echo ATLAS_NETWORK_ERROR & exit /b 15)\r\nif errorlevel 32 (echo ATLAS_NETWORK_CONNECTED & exit /b 14)\r\nif not errorlevel 31 (echo ATLAS_NETWORK_UNKNOWN & exit /b 16)\r\necho ATLAS_NETWORK_DENIED\r\nexit /b 0\r\n";
        File.WriteAllText(script, scriptText, Encoding.ASCII);
        var info = new ProcessStartInfo(executable) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true, WorkingDirectory = project };
        foreach (string arg in new[] { "-c", "windows.sandbox=\"mxc\"", "-c", "permissions.atlas_probe.filesystem={\":minimal\"=\"read\",\":workspace_roots\"=\"write\"}", "-c", "permissions.atlas_probe.network.enabled=false", "-c", "default_permissions=\"atlas_probe\"", "sandbox", "--include-managed-config", "--permission-profile", "atlas_probe", "--", Path.Combine(system, "cmd.exe"), "/d", "/c", script }) info.ArgumentList.Add(arg);
        info.Environment.Clear();
        string systemDrive = Path.GetPathRoot(windows)?.TrimEnd('\\');
        if (systemDrive == null || systemDrive.Length != 2 || !char.IsAsciiLetter(systemDrive[0]) || systemDrive[1] != ':') throw new InvalidOperationException("System drive unavailable.");
        info.Environment["SystemDrive"] = systemDrive; info.Environment["SystemRoot"] = windows; info.Environment["WINDIR"] = windows; info.Environment["PATH"] = system;
        info.Environment["USERPROFILE"] = profile; info.Environment["APPDATA"] = Path.Combine(profile, "appdata");
        info.Environment["LOCALAPPDATA"] = Path.Combine(profile, "local"); info.Environment["TEMP"] = temp; info.Environment["TMP"] = temp; info.Environment["CODEX_HOME"] = Path.Combine(profile, ".codex");
        return info;
    }
    internal static async Task RunOfficialAsync(string packageRoot, string scratchRoot, CancellationToken stop)
    {
        if (!OperatingSystem.IsWindows() || !Path.IsPathFullyQualified(scratchRoot) || !Directory.Exists(scratchRoot)) throw new InvalidOperationException("An isolated Windows scratch directory is required.");
        using var package = VerifiedCodexPackage.Open(packageRoot);
        string scratch = Path.Combine(scratchRoot, "atlas-mxc-" + Guid.NewGuid().ToString("N"));
        var listener = new TcpListener(IPAddress.Loopback, 0); Exception failure = null;
        try
        {
            listener.Start(); int port = ((IPEndPoint)listener.LocalEndpoint).Port;
            // Establish that the same listener is reachable outside the sandbox.
            using (var baseline = new TcpClient(AddressFamily.InterNetwork))
            using (var limit = CancellationTokenSource.CreateLinkedTokenSource(stop))
            {
                limit.CancelAfter(TimeSpan.FromSeconds(3));
                await baseline.ConnectAsync(IPAddress.Loopback, port, limit.Token);
                using var accepted = await listener.AcceptTcpClientAsync(limit.Token);
            }
            var info = BuildProbeStart(package.Executable, scratch, port);
            await RunCaptureAsync(info, stop, mergeErrorWithOutput: true);
            if (!File.Exists(Path.Combine(scratch, "project", "inside.txt")) || File.Exists(Path.Combine(scratch, "outside", "must-not-be-written.txt")) || listener.Pending())
                throw new InvalidOperationException("Scratch sandbox write or loopback network-denial probe did not pass.");
        }
        catch (InvalidOperationException ex) { failure = ex; throw new InvalidOperationException(RedactScratch(ex.Message, scratch)); }
        catch (Exception ex) { failure = ex; throw; }
        finally
        {
            listener.Stop();
            try { if (Directory.Exists(scratch)) Directory.Delete(scratch, true); }
            catch (Exception cleanup) { if (failure == null) throw; Console.Error.WriteLine("Probe cleanup failed after original error: " + cleanup.GetType().Name); }
        }
    }
}
