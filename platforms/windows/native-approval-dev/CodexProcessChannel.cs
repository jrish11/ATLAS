// Direct native-owned Codex app-server JSONL channel. Development only.
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;

namespace Atlas.NativeApprovalDev;

internal sealed class CodexProcessChannel : IDisposable
{
    private const int MaxLine = 1_048_576;
    private static readonly TimeSpan WriteDeadline = TimeSpan.FromSeconds(2);
    private sealed record Outbound(byte[] Bytes, CancellationToken Cancellation, CancellationTokenRegistration Registration, CancellationTokenRegistration RevocationRegistration, Func<TimeSpan> AuthorityRemaining);
    private readonly Process process;
    private readonly Channel<JsonElement> queue = Channel.CreateBounded<JsonElement>(new BoundedChannelOptions(256) { SingleReader = true, SingleWriter = true, FullMode = BoundedChannelFullMode.Wait });
    private readonly Channel<Outbound> outgoing = Channel.CreateBounded<Outbound>(new BoundedChannelOptions(8) { SingleReader = true, SingleWriter = false, FullMode = BoundedChannelFullMode.Wait });
    private readonly CancellationTokenSource stop = new();
    private int aborted;

    internal CodexProcessChannel(ProcessStartInfo info)
    {
        if (info.UseShellExecute || !info.RedirectStandardInput || !info.RedirectStandardOutput || !Path.IsPathFullyQualified(info.FileName)) throw new InvalidOperationException("Invalid provider process configuration.");
        process = Process.Start(info) ?? throw new InvalidOperationException("Provider could not start.");
        _ = Task.Run(ReadLoop);
        _ = Task.Run(WriteLoop);
    }
    private async Task ReadLoop()
    {
        Exception failure = null;
        try
        {
            using var buffer = new MemoryStream(); var stream = process.StandardOutput.BaseStream; byte[] one = new byte[1];
            while (await stream.ReadAsync(one.AsMemory(0, 1), stop.Token) != 0)
            {
                if (one[0] == (byte)'\n')
                {
                    using var doc = JsonDocument.Parse(buffer.ToArray());
                    await queue.Writer.WriteAsync(doc.RootElement.Clone(), stop.Token); buffer.SetLength(0);
                }
                else { if (buffer.Length >= MaxLine) throw new InvalidDataException("Provider frame too long."); buffer.WriteByte(one[0]); }
            }
        }
        catch (Exception ex) when (ex is IOException or ObjectDisposedException or JsonException or InvalidOperationException or OperationCanceledException) { failure = ex; }
        finally { queue.Writer.TryComplete(failure); }
    }

    // Enqueue is bounded and never performs pipe I/O while the authority lock
    // is held. A pending approval cancelled during enqueue/write tears down the
    // entire provider. Already-delivered grants cannot be recalled.
    internal void Send(object payload, CancellationToken cancellation = default, CancellationToken revocation = default, Func<TimeSpan> authorityRemaining = null)
    {
        cancellation.ThrowIfCancellationRequested();
        if (Volatile.Read(ref aborted) != 0) throw new IOException("Provider stopped.");
        byte[] bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(payload) + "\n");
        if (bytes.Length > MaxLine) throw new InvalidDataException("Provider frame too long.");
        var registration = cancellation.Register(() => ThreadPool.QueueUserWorkItem(_ => Abort()));
        var revokedRegistration = revocation.Register(() => ThreadPool.QueueUserWorkItem(_ => Abort()));
        if (cancellation.IsCancellationRequested || revocation.IsCancellationRequested || Volatile.Read(ref aborted) != 0 || !outgoing.Writer.TryWrite(new Outbound(bytes, cancellation, registration, revokedRegistration, authorityRemaining)))
        {
            registration.Dispose(); revokedRegistration.Dispose();
            ThreadPool.QueueUserWorkItem(_ => Abort());
            throw new IOException("Provider write queue unavailable.");
        }
    }
    private async Task WriteLoop()
    {
        try
        {
            await foreach (var item in outgoing.Reader.ReadAllAsync(stop.Token))
            {
                try
                {
                    item.Cancellation.ThrowIfCancellationRequested();
                    // Recheck the host-owned authority at dispatch, not only
                    // when a grant was queued. Revocation tears down pending I/O.
                    TimeSpan authority = item.AuthorityRemaining?.Invoke() ?? WriteDeadline;
                    if (authority <= TimeSpan.Zero) throw new OperationCanceledException();
                    using var deadline = CancellationTokenSource.CreateLinkedTokenSource(stop.Token, item.Cancellation);
                    deadline.CancelAfter(authority < WriteDeadline ? authority : WriteDeadline);
                    // WaitAsync bounds our wait even if an OS stream ignores its
                    // token; Abort closes the process/pipe without a send lock.
                    await process.StandardInput.BaseStream.WriteAsync(item.Bytes.AsMemory(), deadline.Token).AsTask().WaitAsync(deadline.Token);
                    await process.StandardInput.BaseStream.FlushAsync(deadline.Token).WaitAsync(deadline.Token);
                }
                finally { item.Registration.Dispose(); item.RevocationRegistration.Dispose(); }
            }
        }
        catch (Exception ex) when (ex is OperationCanceledException or IOException or ObjectDisposedException or InvalidOperationException or System.ComponentModel.Win32Exception) { Abort(); }
        finally { while (outgoing.Reader.TryRead(out var pending)) { pending.Registration.Dispose(); pending.RevocationRegistration.Dispose(); } }
    }
    internal async Task<JsonElement> ReceiveAsync(TimeSpan timeout, CancellationToken cancellation)
    {
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancellation); limit.CancelAfter(timeout);
        try { return await queue.Reader.ReadAsync(limit.Token); }
        catch (ChannelClosedException) { throw new IOException("Provider disconnected."); }
    }
    private void Abort()
    {
        if (Interlocked.Exchange(ref aborted, 1) != 0) return;
        outgoing.Writer.TryComplete();
        queue.Writer.TryComplete();
        stop.Cancel();
        try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { } catch (System.ComponentModel.Win32Exception) { }
    }
    public void Dispose() { Abort(); }
}
