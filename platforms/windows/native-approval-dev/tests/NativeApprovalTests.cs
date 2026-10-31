using System.Security.Cryptography;
using System.ComponentModel;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Atlas.NativeApprovalDev;

static class NativeApprovalTests
{
    static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    static void Require(bool value, string name) { if (!value) throw new Exception("Failed: " + name); }
    static ApprovalRequest Request(ApprovalSession s, string nonce, string payload = "{\"id\":\"fixture\",\"method\":\"item/fileChange/requestApproval\",\"params\":{\"threadId\":\"thread\",\"turnId\":\"turn\"}}") => new(s.Id, nonce, s.Task, s.Project, s.Scope, payload, Hash(payload));

    [StructLayout(LayoutKind.Sequential)] struct FixtureSecurity { public int Length; public IntPtr Descriptor; public int Inherit; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateEventW(ref FixtureSecurity attributes, bool manualReset, bool initialState, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint WaitForSingleObject(SafeFileHandle handle, uint milliseconds);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern uint GetShortPathNameW(string path, StringBuilder shortPath, uint length);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool DeviceIoControl(SafeFileHandle handle, uint code, byte[] input, uint size, IntPtr output, uint outputSize, out uint returned, IntPtr overlapped);
    [DllImport("kernel32.dll", EntryPoint = "DeviceIoControl", SetLastError = true)]
    static extern bool ReadReparsePoint(SafeFileHandle handle, uint code, IntPtr input, uint size, byte[] output, uint outputSize, out uint returned, IntPtr overlapped);
    static bool ExpectedMutationDenial(int error) => error is 5 or 32 or 1314;
    static void CleanupWithoutMasking(Action cleanup, Exception primary)
    {
        try { cleanup(); }
        catch (Exception ex) { if (primary == null) throw; Console.Error.WriteLine("Cleanup failed after original error: " + ex); }
    }
    static bool WithinScratch(string path, string scratch) => Path.GetFullPath(path).StartsWith(Path.TrimEndingDirectorySeparator(Path.GetFullPath(scratch)) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);

    // Attempt an actual in-place junction conversion of a disposable empty
    // directory while the guard holds it. If Windows denies mutation, that is
    // also a passing outcome; if it succeeds the guard must detect the change.
    static bool TrySetJunction(string directory, string target)
    {
        using var h = CreateFileW(directory, 0x40000000, 3, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
        if (h.IsInvalid) { int error = Marshal.GetLastWin32Error(); if (ExpectedMutationDenial(error)) { Console.WriteLine("Mutation handle denied, Win32 " + error); return false; } throw new Win32Exception(error, "Open scratch junction fixture failed"); }
        byte[] sub = Encoding.Unicode.GetBytes(@"\??\" + target);
        byte[] print = Encoding.Unicode.GetBytes(target);
        using var memory = new MemoryStream(); using var writer = new BinaryWriter(memory);
        writer.Write(0xA0000003u); writer.Write((ushort)(8 + sub.Length + 2 + print.Length + 2)); writer.Write((ushort)0);
        writer.Write((ushort)0); writer.Write((ushort)sub.Length); writer.Write((ushort)(sub.Length + 2)); writer.Write((ushort)print.Length);
        writer.Write(sub); writer.Write((ushort)0); writer.Write(print); writer.Write((ushort)0);
        byte[] buffer = memory.ToArray();
        if (DeviceIoControl(h, 0x000900A4, buffer, (uint)buffer.Length, IntPtr.Zero, 0, out _, IntPtr.Zero)) return true;
        int failure = Marshal.GetLastWin32Error();
        if (ExpectedMutationDenial(failure)) { Console.WriteLine("Reparse mutation denied, Win32 " + failure); return false; }
        throw new Win32Exception(failure, "Setting scratch junction failed; fixture layout or filesystem may be unsupported");
    }
    static void RemoveFixtureJunction(string directory, string target, string scratch)
    {
        if (!WithinScratch(directory, scratch) || !WithinScratch(target, scratch)) throw new InvalidOperationException("Fixture paths must remain inside scratch.");
        using var h = CreateFileW(directory, 0x40000000, 3, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
        if (h.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "Cannot open scratch junction for cleanup");
        byte[] data = new byte[16384];
        if (!ReadReparsePoint(h, 0x000900A8, IntPtr.Zero, 0, data, (uint)data.Length, out uint received, IntPtr.Zero)) throw new Win32Exception(Marshal.GetLastWin32Error(), "Cannot read scratch reparse point");
        if (received < 16 || BitConverter.ToUInt32(data, 0) != 0xA0000003u) throw new InvalidDataException("Unexpected scratch reparse tag; refusing removal.");
        int offset = BitConverter.ToUInt16(data, 8), length = BitConverter.ToUInt16(data, 10);
        bool validTarget = offset % 2 == 0 && length % 2 == 0 && 16 + offset + length <= received &&
            string.Equals(Encoding.Unicode.GetString(data, 16 + offset, length), @"\??\" + target, StringComparison.OrdinalIgnoreCase);
        // Delete only the exact mount-point tag just created by this fixture;
        // unlike Directory.Delete, this does not traverse the junction target.
        byte[] header = new byte[8]; BitConverter.GetBytes(0xA0000003u).CopyTo(header, 0);
        if (!DeviceIoControl(h, 0x000900AC, header, (uint)header.Length, IntPtr.Zero, 0, out _, IntPtr.Zero)) throw new Win32Exception(Marshal.GetLastWin32Error(), "Cannot remove scratch junction tag");
        if (!validTarget) throw new InvalidDataException("Scratch junction target readback did not match the fixture.");
        if (!Directory.Exists(target)) throw new IOException("Scratch junction target disappeared.");
    }

    static void Main(string[] args)
    {
        if (args.Length == 3 && args[0] == "--mxc-probe")
        {
            NativeSandboxProbe.RunOfficialAsync(Path.GetFullPath(args[1]), Path.GetFullPath(args[2]), CancellationToken.None).GetAwaiter().GetResult();
            Console.WriteLine("MXC scratch write and loopback denial probes passed; other isolation remains unverified.");
            return;
        }
        Require(!NativeOwnerBroker.Enabled, "production broker remains disabled");
        try { NativeOwnerBroker.RunAsync(null, "fixture", "unused", "unused", CancellationToken.None).GetAwaiter().GetResult(); throw new Exception("Disabled broker started"); }
        catch (InvalidOperationException) { }
        byte[] digestFixture = Encoding.UTF8.GetBytes("fixture");
        string digest = Convert.ToHexString(SHA256.HashData(digestFixture)).ToLowerInvariant();
        Require(PinnedCodexExecutable.MatchesDigest(new MemoryStream(digestFixture), digest), "official digest verification primitive");
        Require(!PinnedCodexExecutable.MatchesDigest(new MemoryStream(Encoding.UTF8.GetBytes("tampered")), digest), "tampered digest rejected");
        var now = DateTimeOffset.FromUnixTimeSeconds(1000);
        ulong ticks = 1000;
        var project = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "atlas-fixture"));
        ApprovalSession New() { var session = new ApprovalSession("fixture task", project, "workspace-write; network-disabled", () => now, TimeSpan.FromMinutes(2), () => ticks); Require(session.BindTurn("thread", "turn"), "bind turn"); return session; }
        var s = New(); var r = Request(s, new string('a', 32));
        Require(s.Decide(r, _ => true).Decision == "accept", "approved request");
        Require(s.Decide(r, _ => true).Decision != "accept", "replay rejected");
        var wrong = Request(s, new string('b', 32)) with { Project = project + "-other" };
        bool prompted = false; Require(s.Decide(wrong, _ => { prompted = true; return true; }).Decision != "accept" && !prompted, "project mismatch");
        var wrongTask = Request(s, new string('2', 32)) with { Task = "different task" };
        Require(s.Decide(wrongTask, _ => true).Decision != "accept", "task mismatch");
        var wrongScope = Request(s, new string('3', 32)) with { Scope = "unrestricted" };
        Require(s.Decide(wrongScope, _ => true).Decision != "accept", "scope mismatch");
        var wrongTurn = Request(s, new string('4', 32), "{\"id\":\"fixture\",\"method\":\"item/fileChange/requestApproval\",\"params\":{\"threadId\":\"thread\",\"turnId\":\"other\"}}");
        Require(s.Decide(wrongTurn, _ => true).Decision != "accept", "turn mismatch");
        var duplicate = Request(s, new string('6', 32), "{\"id\":\"fixture\",\"method\":\"item/fileChange/requestApproval\",\"params\":{\"threadId\":\"thread\",\"turnId\":\"other\",\"turnId\":\"turn\"}}");
        Require(s.Decide(duplicate, _ => true).Decision != "accept", "duplicate JSON property");
        var unbound = new ApprovalSession("fixture task", project, "workspace-write; network-disabled", () => now, TimeSpan.FromMinutes(2));
        Require(unbound.Decide(Request(unbound, new string('5', 32)), _ => true).Decision != "accept", "unbound turn");
        var tampered = Request(s, new string('c', 32)) with { Payload = "changed" };
        Require(s.Decide(tampered, _ => true).Decision != "accept", "payload mismatch");
        var rejected = Request(s, new string('d', 32));
        Require(s.Decide(rejected, _ => false).Decision != "accept", "native denial");
        var cancelled = Request(s, new string('e', 32));
        Require(s.Decide(cancelled, _ => { s.Revoke(); return true; }).Decision != "accept", "revocation during dialog");
        var rollback = New(); now = now.AddDays(-10);
        Require(rollback.Decide(Request(rollback, new string('7', 32)), _ => true).Decision == "accept", "wall clock rollback leaves elapsed lease intact");
        var forward = New(); now = now.AddDays(20);
        Require(forward.Decide(Request(forward, new string('8', 32)), _ => true).Decision == "accept", "wall clock forward does not set authority expiry");
        var expired = New(); now = now.AddDays(-30); ticks += 180_000;
        Require(expired.Decide(Request(expired, new string('f', 32)), _ => true).Decision != "accept", "expired session");
        var elapsedDeadline = new ElapsedDeadline(TimeSpan.FromSeconds(30), () => ticks);
        ticks += 30_001; Require(elapsedDeadline.Remaining() == TimeSpan.Zero, "sleep-equivalent elapsed request deadline");
        var regression = new ElapsedDeadline(TimeSpan.FromSeconds(30), () => ticks);
        ticks -= 1; Require(regression.Remaining() == TimeSpan.Zero, "elapsed counter regression fails closed");
        var controls = New();
        Require(controls.Decide(Request(controls, new string('1', 32), "bad\u202etext"), _ => true).Decision != "accept", "spoofing control denied");
        if (args.Length != 3) throw new ArgumentException("Pass absolute Python executable, fake worker and fake provider paths.");
        var pipeSession = new ApprovalSession("fixture task", project, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromMinutes(2));
        Require(pipeSession.BindTurn("thread", "turn"), "bind fake child turn");
        bool nativeAsked = false;
        using var host = new PrivateApprovalHost(pipeSession);
        host.Start(Path.GetFullPath(args[0]), Path.GetFullPath(args[1]));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        host.ServeAsync(_ => { nativeAsked = true; return true; }, timeout.Token).GetAwaiter().GetResult();
        Require(nativeAsked && host.WaitForExit(3000) == 0, "inherited anonymous pipe and fake child");
        string root = Environment.GetEnvironmentVariable("ATLAS_NATIVE_TEST_ROOT") ?? throw new Exception("Set ATLAS_NATIVE_TEST_ROOT to a scratch folder outside the user profile and app directory.");
        string scratch = Path.Combine(root, "atlas-native-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(scratch);
        Exception scratchFailure = null;
        try
        {
            // Only change disposable scratch data and fake environment values.
            var original = new Dictionary<string, string>();
            var canaries = new[] { "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "SSH_AUTH_SOCK", "HTTPS_PROXY", "OPENAI_BASE_URL", "CODEX_HOME" };
            try
            {
                foreach (string key in canaries) { original[key] = Environment.GetEnvironmentVariable(key); Environment.SetEnvironmentVariable(key, "ATLAS_FAKE_CANARY"); }
                var start = NativeCodexTurn.CreateProviderStart(Path.GetFullPath(args[0]), "atlas_" + Guid.NewGuid().ToString("N"));
                foreach (string key in canaries) Require(!start.Environment.ContainsKey(key), "secret/proxy environment absent: " + key);
                Require(start.Environment.ContainsKey("SystemRoot") && start.Environment.ContainsKey("USERPROFILE"), "required platform environment");
            }
            finally { foreach (var pair in original) Environment.SetEnvironmentVariable(pair.Key, pair.Value); }
            string layoutRoot = Path.Combine(scratch, "layout-test");
            var probeInfo = NativeSandboxProbe.BuildProbeStart(Path.GetFullPath(args[0]), layoutRoot, 32123);
            string probeTemp = Path.GetFullPath(probeInfo.Environment["TEMP"]), forbidden = Path.GetFullPath(Path.Combine(layoutRoot, "outside"));
            Require(probeTemp == Path.GetFullPath(Path.Combine(layoutRoot, "runtime-temp")) && probeInfo.Environment["TMP"] == probeTemp, "probe temp isolated from outside target");
            Require(!forbidden.StartsWith(Path.TrimEndingDirectorySeparator(probeTemp) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase), "outside target is not under temp");
            string redacted = NativeSandboxProbe.RedactScratch(layoutRoot + " " + layoutRoot.Replace("\\", "\\\\"), layoutRoot);
            Require(redacted == "<scratch> <scratch>", "literal and JSON-escaped scratch paths redacted");
            string isolatedProfile = Path.GetFullPath(Path.Combine(layoutRoot, "profile"));
            string codexHome = Path.GetFullPath(probeInfo.Environment["CODEX_HOME"]);
            Require(Directory.Exists(codexHome) && codexHome == Path.Combine(isolatedProfile, ".codex"), "isolated CODEX_HOME exists within profile");
            Require(probeInfo.ArgumentList.Contains("permissions.atlas_probe.network.enabled=false") && probeInfo.ArgumentList.Contains("windows.sandbox=\"mxc\""), "explicit MXC network-disabled policy");
            string commandText = File.ReadAllText(Path.Combine(layoutRoot, "project", "fixture.cmd"));
            Require(commandText.Contains("127.0.0.1", StringComparison.Ordinal) && commandText.Contains("32123", StringComparison.Ordinal) && commandText.Contains("exit 33", StringComparison.Ordinal), "loopback denial fixture distinguishes socket errors");
            const string officialManifest = "{\r\n  \"layoutVersion\": 1,\r\n  \"version\": \"0.166.0\",\r\n  \"target\": \"x86_64-pc-windows-msvc\",\r\n  \"variant\": \"codex\",\r\n  \"entrypoint\": \"bin/codex.exe\",\r\n  \"execServer\": \"bin/codex-exec-server.exe\",\r\n  \"resourcesDir\": \"codex-resources\",\r\n  \"pathDir\": \"codex-path\"\r\n}\r\n";
            bool ManifestMatches(string text) => PinnedCodexExecutable.MatchesDigest(new MemoryStream(Encoding.UTF8.GetBytes(text)), VerifiedCodexPackage.ManifestSha256);
            Require(ManifestMatches(officialManifest), "exact official package manifest accepted");
            Require(!ManifestMatches(officialManifest.Replace("bin/codex-exec-server.exe", "bin/changed.exe")), "tampered execServer denied");
            Require(!ManifestMatches(officialManifest.Replace("codex-path", "changed-path")), "tampered pathDir denied");
            string incompletePackage = Path.Combine(scratch, "incomplete-package"); Directory.CreateDirectory(incompletePackage);
            File.WriteAllBytes(Path.Combine(incompletePackage, "codex-package.json"), Encoding.UTF8.GetBytes(officialManifest));
            bool missingRejected = false;
            try { using var missing = VerifiedCodexPackage.Open(incompletePackage); }
            catch (IOException) { missingRejected = true; }
            Require(missingRejected, "incomplete official package rejected");
            string target = Path.Combine(scratch, "target"); string selected = Path.Combine(scratch, "project-long-directory");
            Directory.CreateDirectory(target); Directory.CreateDirectory(selected);
            bool pathRejected = false;
            try { using var bad = WindowsProjectGuard.Open(selected + "."); } catch (InvalidOperationException) { pathRejected = true; }
            Require(pathRejected, "trailing-dot alias denied");
            var shortPath = new StringBuilder(32768);
            uint shortLength = GetShortPathNameW(selected, shortPath, (uint)shortPath.Capacity);
            if (shortLength > 0 && shortLength < shortPath.Capacity && !string.Equals(selected, shortPath.ToString(), StringComparison.OrdinalIgnoreCase))
            {
                pathRejected = false; try { using var bad = WindowsProjectGuard.Open(shortPath.ToString()); } catch (InvalidOperationException) { pathRejected = true; }
                Require(pathRejected, "8.3 project alias denied");
            }
            else Console.WriteLine("8.3 alias test unavailable on this volume; long-path and trailing-dot tests remain active.");
            var oldCodexHome = Environment.GetEnvironmentVariable("CODEX_HOME");
            try
            {
                Environment.SetEnvironmentVariable("CODEX_HOME", selected);
                pathRejected = false; try { using var bad = WindowsProjectGuard.Open(selected); } catch (InvalidOperationException) { pathRejected = true; }
                Require(pathRejected, "protected project denied");
            }
            finally { Environment.SetEnvironmentVariable("CODEX_HOME", oldCodexHome); }
            if (!WithinScratch(selected, scratch) || !WithinScratch(target, scratch)) throw new InvalidOperationException("Mutation fixture escaped scratch.");
            bool mutated = false; Exception mutationFailure = null;
            try
            {
                using var identity = WindowsProjectGuard.Open(selected);
                mutated = TrySetJunction(selected, target);
                if (mutated)
                {
                    pathRejected = false;
                    try { identity.EnsureActive(); }
                    catch (Exception ex) when (ex is InvalidOperationException or Win32Exception) { pathRejected = true; Console.WriteLine("Guard rejected mutation: " + ex.GetType().Name); }
                    Require(pathRejected, "in-place reparse mutation detected");
                }
                else { identity.EnsureActive(); Console.WriteLine("OS denied this scratch in-place reparse mutation while guarded; other mutation methods remain unverified."); }
            }
            catch (Exception ex) { mutationFailure = ex; throw; }
            finally { if (mutated) CleanupWithoutMasking(() => RemoveFixtureJunction(selected, target, scratch), mutationFailure); }
            foreach (string frameKind in new[] { "thread/start", "turn/start", "approval" })
            {
                string marker = Path.Combine(scratch, "project-boundary-" + Guid.NewGuid().ToString("N"));
                var owner = new ApprovalSession("fixture task", selected, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromMinutes(2));
                var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
                info.ArgumentList.Add(Path.GetFullPath(args[2]));
                info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
                info.Environment["ATLAS_FIXTURE_PROJECT"] = selected;
                info.Environment["ATLAS_FIXTURE_MODE"] = "synchronized_read";
                info.Environment["ATLAS_FIXTURE_MARKER"] = marker;
                var guard = WindowsProjectGuard.Open(selected);
                using var writerReached = new ManualResetEventSlim(false);
                using var proceed = new ManualResetEventSlim(false);
                int checks = 0;
                using var provider = new CodexProcessChannel(info, () => { writerReached.Set(); if (!proceed.Wait(TimeSpan.FromSeconds(5))) throw new InvalidOperationException("Fixture release timed out."); });
                bool fixtureMutated = false; Exception fixtureFailure = null;
                try
                {
                    provider.Send(new { data = new string('x', 65_536) });
                    object frame = frameKind == "approval" ? new { id = "fixture", result = new { decision = "accept" } } : new { id = "fixture", method = frameKind };
                    Require(owner.CommitIfActive(CancellationToken.None, () => provider.Send(frame, CancellationToken.None, owner.RevocationToken, () => { Interlocked.Increment(ref checks); return NativeCodexTurn.DispatchAuthority(owner, guard); })), "project-bound frame queued");
                    var ack = provider.ReceiveAsync(TimeSpan.FromSeconds(5), CancellationToken.None).GetAwaiter().GetResult();
                    Require(ack.TryGetProperty("fixture", out var ackType) && ackType.GetString() == "filler-consumed", "fake child consumed filler");
                    Require(writerReached.Wait(TimeSpan.FromSeconds(5)), "writer reached privileged frame");
                    fixtureMutated = TrySetJunction(selected, target);
                    if (!fixtureMutated) { guard.Dispose(); Console.WriteLine("OS denied in-place mutation; checking disposed project identity instead for " + frameKind); }
                    proceed.Set();
                    try { provider.ReceiveAsync(TimeSpan.FromSeconds(5), CancellationToken.None).GetAwaiter().GetResult(); throw new Exception("Provider unexpectedly produced output"); }
                    catch (IOException) { }
                    Require(Volatile.Read(ref checks) >= 2, "writer rechecked project after mutation");
                    Require(!File.Exists(marker), "changed project prevented " + frameKind);
                }
                catch (Exception ex) { fixtureFailure = ex; throw; }
                finally
                {
                    proceed.Set(); provider.Dispose(); guard.Dispose();
                    if (fixtureMutated) CleanupWithoutMasking(() => RemoveFixtureJunction(selected, target, scratch), fixtureFailure);
                    if (File.Exists(marker)) File.Delete(marker);
                }
            }
            foreach (string mode in new[] { "ok", "unsafe", "weak_sandbox", "stale", "cancel", "duplicate", "conflict", "late", "duplicate_cancel" })
            {
                using var guard = WindowsProjectGuard.Open(scratch);
                var owner = new ApprovalSession("fixture task", guard.Project, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromMinutes(2));
                string profile = "atlas_" + Guid.NewGuid().ToString("N");
                var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
                info.ArgumentList.Add(Path.GetFullPath(args[2]));
                info.Environment["ATLAS_FIXTURE_PROFILE"] = profile;
                info.Environment["ATLAS_FIXTURE_PROJECT"] = guard.Project;
                info.Environment["ATLAS_FIXTURE_MODE"] = mode;
                using var provider = new CodexProcessChannel(info);
                var native = new NativeCodexTurn(owner, guard, provider, profile);
                using var cancel = new CancellationTokenSource(TimeSpan.FromSeconds(20));
                bool asked = false; int promptCount = 0;
                try
                {
                    var result = native.RunAsync(_ => { asked = true; promptCount++; if (mode == "cancel" || mode == "duplicate_cancel") cancel.Cancel(); return true; }, cancel.Token).GetAwaiter().GetResult();
                    if (mode == "ok") Require(asked && result.Status == "completed", "native provider approval");
                    if (mode == "stale") Require(!asked && result.Status == "approval denied", "stale provider turn denied");
                    if (mode == "cancel" || mode == "duplicate_cancel") Require(asked && promptCount == 1 && result.Status.StartsWith("stopped"), "cancel during native prompt");
                    if (mode == "late") Require(!asked && result.Status == "completed", "late request not prompted");
                    if (mode == "unsafe" || mode == "weak_sandbox" || mode == "duplicate" || mode == "conflict") throw new Exception("Unsafe provider input accepted");
                }
                catch (InvalidDataException) when (mode == "unsafe" || mode == "weak_sandbox") { Require(!asked, "unsafe provider not prompted"); }
                catch (InvalidDataException) when (mode == "duplicate" || mode == "conflict") { Require(promptCount == 1, "duplicate provider request not reprompted"); }
            }
        }
        catch (Exception ex) { scratchFailure = ex; throw; }
        finally { CleanupWithoutMasking(() => Directory.Delete(scratch, true), scratchFailure); }
        // Bounded diagnostic capture also uses the contained launcher.
        {
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project; info.Environment["ATLAS_FIXTURE_MODE"] = "argv_echo";
            string result = NativeSandboxProbe.RunCaptureAsync(info, CancellationToken.None).GetAwaiter().GetResult();
            Require(result.Contains("arguments", StringComparison.Ordinal), "contained probe capture fake output");
        }
        // Only an explicit probe merges stderr; the ordinary provider keeps it private.
        foreach (bool merged in new[] { false, true })
        {
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project; info.Environment["ATLAS_FIXTURE_MODE"] = "stderr_probe";
            string output = NativeSandboxProbe.RunCaptureAsync(info, CancellationToken.None, merged).GetAwaiter().GetResult();
            Require(output.Contains("FAKE_MXC_DIAGNOSTIC", StringComparison.Ordinal) == merged, "probe-only diagnostic merge");
        }
        // Credential-free probe runs through the same suspended/job-contained
        // launcher; this fake does not establish any operating-system sandbox.
        {
            string fakeRoot = Path.Combine(root, "atlas-probe-fake-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(fakeRoot);
            string inside = Path.Combine(fakeRoot, "inside"), outside = Path.Combine(fakeRoot, "outside");
            try
            {
                var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
                info.ArgumentList.Add(Path.GetFullPath(args[2]));
                info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
                info.Environment["ATLAS_FIXTURE_PROJECT"] = fakeRoot; info.Environment["ATLAS_FIXTURE_MODE"] = "sandbox_fake"; info.Environment["ATLAS_FAKE_INSIDE"] = inside;
                NativeSandboxProbe.VerifyContainedAsync(info, inside, outside, CancellationToken.None).GetAwaiter().GetResult();
            }
            finally { Directory.Delete(fakeRoot, true); }
        }
        // Windows CRT quoting round-trips spaces, quotes and trailing slashes.
        {
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            string[] expected = { "two words", "quoted\"word", @"tail\" };
            foreach (string value in expected) info.ArgumentList.Add(value);
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project; info.Environment["ATLAS_FIXTURE_MODE"] = "argv_echo";
            using var provider = new CodexProcessChannel(info);
            var reply = provider.ReceiveAsync(TimeSpan.FromSeconds(5), CancellationToken.None).GetAwaiter().GetResult();
            Require(reply.GetProperty("arguments").EnumerateArray().Select(x => x.GetString()).SequenceEqual(expected), "Windows command argument quoting");
        }
        // An inheritable parent event must not be among the explicitly passed
        // standard handles, even when the parent exposes its numeric value.
        {
            var attr = new FixtureSecurity { Length = Marshal.SizeOf<FixtureSecurity>(), Inherit = 1 };
            using var canary = CreateEventW(ref attr, true, false, null);
            Require(!canary.IsInvalid, "create inheritable canary event");
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project;
            info.Environment["ATLAS_FIXTURE_MODE"] = "handle_canary";
            info.Environment["ATLAS_CANARY_HANDLE"] = canary.DangerousGetHandle().ToInt64().ToString(System.Globalization.CultureInfo.InvariantCulture);
            using var provider = new CodexProcessChannel(info);
            var reply = provider.ReceiveAsync(TimeSpan.FromSeconds(5), CancellationToken.None).GetAwaiter().GetResult();
            Require(reply.GetProperty("canary_attempted").GetBoolean(), "fake child attempted inherited canary");
            Require(WaitForSingleObject(canary, 100) == 0x102, "unlisted inheritable event absent from child");
        }
        // A pre-resume failure must terminate the suspended child before its
        // first instruction; its marker must never be created.
        {
            string marker = Path.Combine(root, "atlas-suspended-marker-" + Guid.NewGuid().ToString("N"));
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project;
            info.Environment["ATLAS_FIXTURE_MODE"] = "start_marker";
            info.Environment["ATLAS_FIXTURE_MARKER"] = marker;
            bool failed = false;
            try { using var unexpected = new CodexProcessChannel(info, failBeforeResumeForTest: true); }
            catch (InvalidOperationException) { failed = true; }
            Require(failed, "failure before resume reported");
            System.Threading.Thread.Sleep(300);
            Require(!File.Exists(marker), "suspended child never started on containment failure");
            if (File.Exists(marker)) File.Delete(marker);
        }
        // Fake provider launches a sleeping fake descendant; closing the job
        // must stop it. This does not test escape during the pre-assignment race.
        {
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project;
            info.Environment["ATLAS_FIXTURE_MODE"] = "spawn_child";
            using var provider = new CodexProcessChannel(info);
            var notice = provider.ReceiveAsync(TimeSpan.FromSeconds(5), CancellationToken.None).GetAwaiter().GetResult();
            int childPid = notice.GetProperty("child_pid").GetInt32();
            using var descendant = System.Diagnostics.Process.GetProcessById(childPid);
            provider.Dispose();
            Require(descendant.WaitForExit(5000), "job terminates fake descendant");
        }
        // Fill a never-reading child's pipe with one large queued frame. The
        // authority lock and process teardown must remain independently usable.
        {
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project;
            info.Environment["ATLAS_FIXTURE_MODE"] = "never_read";
            using var provider = new CodexProcessChannel(info);
            using var cancellation = new CancellationTokenSource();
            var authority = new ApprovalSession("fixture task", project, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromMinutes(2));
            Require(authority.CommitIfActive(cancellation.Token, () => provider.Send(new { data = new string('x', 900_000) }, cancellation.Token)), "bounded enqueue under authority");
            System.Threading.Thread.Sleep(300);
            var clock = System.Diagnostics.Stopwatch.StartNew();
            cancellation.Cancel();
            var revoke = System.Threading.Tasks.Task.Run(() => { authority.Revoke(); provider.Dispose(); });
            Require(revoke.Wait(TimeSpan.FromSeconds(3)) && clock.Elapsed < TimeSpan.FromSeconds(3), "blocked provider cancellation and teardown bounded");
            Require(!authority.CommitIfActive(cancellation.Token, () => throw new Exception("revoked authority sent")), "cancelled authority cannot grant");
            try { provider.ReceiveAsync(TimeSpan.FromSeconds(2), CancellationToken.None).GetAwaiter().GetResult(); throw new Exception("closed provider produced data"); }
            catch (IOException) { }
        }
        foreach (string cause in new[] { "revoke", "expire" })
        {
            string marker = Path.Combine(root, "atlas-grant-marker-" + Guid.NewGuid().ToString("N"));
            ulong grantTicks = 10_000;
            var authority = new ApprovalSession("fixture task", project, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromSeconds(30), () => grantTicks);
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project;
            info.Environment["ATLAS_FIXTURE_MODE"] = "delayed_read";
            info.Environment["ATLAS_FIXTURE_MARKER"] = marker;
            using var provider = new CodexProcessChannel(info);
            try
            {
                provider.Send(new { data = new string('x', 900_000) });
                Require(authority.CommitIfActive(CancellationToken.None, () => provider.Send(new { id = "fixture", result = new { decision = "accept" } }, CancellationToken.None, authority.RevocationToken, authority.AuthorityRemaining)), "queued fixture grant");
                if (cause == "revoke") authority.Revoke(); else grantTicks += 30_001;
                System.Threading.Thread.Sleep(1800); // child would have drained by now
                Require(!File.Exists(marker), "queued grant blocked after " + cause);
            }
            finally { provider.Dispose(); if (File.Exists(marker)) File.Delete(marker); }
        }
        // Deterministically revoke after the writer's initial authority check
        // but before it links/checks the token and starts the actual write.
        {
            string marker = Path.Combine(root, "atlas-boundary-marker-" + Guid.NewGuid().ToString("N"));
            var authority = new ApprovalSession("fixture task", project, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromMinutes(2));
            var info = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[0])) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true };
            info.ArgumentList.Add(Path.GetFullPath(args[2]));
            info.Environment["ATLAS_FIXTURE_PROFILE"] = "atlas_" + Guid.NewGuid().ToString("N");
            info.Environment["ATLAS_FIXTURE_PROJECT"] = project;
            info.Environment["ATLAS_FIXTURE_MODE"] = "delayed_read";
            info.Environment["ATLAS_FIXTURE_MARKER"] = marker;
            using var reached = new ManualResetEventSlim(false);
            using var provider = new CodexProcessChannel(info, () => { authority.Revoke(); reached.Set(); });
            try
            {
                Require(authority.CommitIfActive(CancellationToken.None, () => provider.Send(new { id = "fixture", result = new { decision = "accept" } }, CancellationToken.None, authority.RevocationToken, authority.AuthorityRemaining)), "boundary fixture grant queued");
                Require(reached.Wait(TimeSpan.FromSeconds(3)), "pre-write revocation fixture reached");
                System.Threading.Thread.Sleep(1800);
                Require(!File.Exists(marker), "revocation between check and write blocked grant");
            }
            finally { provider.Dispose(); if (File.Exists(marker)) File.Delete(marker); }
        }
        Console.WriteLine("Native approval and fake provider tests passed; no real provider or computer action invoked.");
    }
}
