// Legacy worker-supplied-request experiment. PROHIBITED for production or
// provider grants: request provenance is not independently correlated and
// cancellation during a prompt can race the synchronous response. Deliberately
// not connected to app startup. Do not enable or use as an approval authority.
using System.Diagnostics;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace Atlas.NativeApprovalDev;

internal sealed class PrivateApprovalHost : IDisposable
{
    private const int MaxLine = 16384;
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = false };
    private readonly ApprovalSession session;
    private readonly AnonymousPipeServerStream toChild = new(PipeDirection.Out, HandleInheritability.Inheritable);
    private readonly AnonymousPipeServerStream fromChild = new(PipeDirection.In, HandleInheritability.Inheritable);
    private Process child;
    private bool disposed;

    internal PrivateApprovalHost(ApprovalSession nativeApprovedSession) => session = nativeApprovedSession ?? throw new ArgumentNullException(nameof(nativeApprovedSession));

    // Executable and worker path must be supplied by the trusted native host,
    // not by a WebView or model. No request path invokes this in the preview.
    internal void Start(string python, string worker)
    {
        if (disposed || child != null || !Path.IsPathFullyQualified(python) || !Path.IsPathFullyQualified(worker) || !File.Exists(python) || !File.Exists(worker))
            throw new InvalidOperationException("Cannot launch approval worker.");
        var si = new ProcessStartInfo(python) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(worker)! };
        si.ArgumentList.Add(worker);
        si.ArgumentList.Add("--approval-read-handle"); si.ArgumentList.Add(toChild.GetClientHandleAsString());
        si.ArgumentList.Add("--approval-write-handle"); si.ArgumentList.Add(fromChild.GetClientHandleAsString());
        try
        {
            child = Process.Start(si) ?? throw new InvalidOperationException("Could not start worker.");
            toChild.DisposeLocalCopyOfClientHandle(); fromChild.DisposeLocalCopyOfClientHandle();
            Write(new { session = session.Id, task = session.Task, project = session.Project, scope = session.Scope });
        }
        catch { session.Revoke(); Dispose(); throw; }
    }

    private void Write(object message)
    {
        byte[] line = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message, Json) + "\n");
        if (line.Length > MaxLine) throw new InvalidDataException("Approval response too long.");
        toChild.Write(line); toChild.Flush();
    }

    internal async Task ServeAsync(Func<ApprovalRequest, bool> nativePrompt, CancellationToken cancel)
    {
        if (child == null || disposed) throw new InvalidOperationException("Worker not started.");
        try
        {
            while (!cancel.IsCancellationRequested && !child.HasExited)
            {
                string line = await ReadBoundedAsync(fromChild, cancel);
                if (line == null) break;
                ApprovalRequest request;
                try { request = JsonSerializer.Deserialize<ApprovalRequest>(line, Json); }
                catch (JsonException) { break; }
                Write(session.Decide(request, nativePrompt));
            }
        }
        catch (Exception ex) when (ex is IOException or OperationCanceledException or ObjectDisposedException or InvalidDataException or DecoderFallbackException) { }
        finally { session.Revoke(); }
    }

    private static async Task<string> ReadBoundedAsync(Stream input, CancellationToken cancel)
    {
        using var data = new MemoryStream();
        byte[] one = new byte[1];
        while (data.Length <= MaxLine)
        {
            int n = await input.ReadAsync(one.AsMemory(0, 1), cancel);
            if (n == 0) return null;
            if (one[0] == (byte)'\n') return new UTF8Encoding(false, true).GetString(data.ToArray());
            data.WriteByte(one[0]);
        }
        throw new InvalidDataException("Approval request too long.");
    }

    internal int? WaitForExit(int milliseconds)
    {
        if (child == null || !child.WaitForExit(milliseconds)) return null;
        return child.ExitCode;
    }

    internal void Cancel() { session.Revoke(); try { if (child != null && !child.HasExited) child.Kill(true); } catch (InvalidOperationException) { } catch (System.ComponentModel.Win32Exception) { } }
    public void Dispose()
    {
        if (disposed) return;
        disposed = true; Cancel(); toChild.Dispose(); fromChild.Dispose(); child?.Dispose();
    }
}
