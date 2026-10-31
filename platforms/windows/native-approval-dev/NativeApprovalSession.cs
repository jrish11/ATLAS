// Development prototype only. Not wired into the restricted Windows preview.
// A native host owns this state; no file, WebView message or environment flag
// can issue a grant. Provider sandbox enforcement remains a separate gate.
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Atlas.NativeApprovalDev;

// GetTickCount64 explicitly includes Windows sleep/hibernation and is not
// adjusted with wall clock changes (unlike .NET 11 Environment.TickCount64).
internal sealed class ElapsedDeadline
{
    [DllImport("kernel32.dll")]
    private static extern ulong GetTickCount64();
    private readonly Func<ulong> elapsed;
    private readonly ulong start, duration;
    private readonly object gate = new();
    private ulong last;
    private bool invalid;
    internal ElapsedDeadline(TimeSpan interval, Func<ulong> elapsed = null)
    {
        if (interval <= TimeSpan.Zero || interval.TotalMilliseconds > uint.MaxValue) throw new ArgumentOutOfRangeException(nameof(interval));
        this.elapsed = elapsed ?? (() => GetTickCount64());
        duration = (ulong)Math.Ceiling(interval.TotalMilliseconds);
        start = this.elapsed();
        last = start;
    }
    internal TimeSpan Remaining()
    {
        lock (gate)
        {
            ulong now = elapsed();
            // An unexpected counter regression permanently invalidates the lease.
            if (now < last) invalid = true;
            last = now;
            if (invalid || now - start >= duration) return TimeSpan.Zero;
            return TimeSpan.FromMilliseconds(duration - (now - start));
        }
    }
}

internal sealed record ApprovalRequest(string Session, string Nonce, string Task, string Project, string Scope, string Payload, string Digest);
internal sealed record ApprovalResponse(string Session, string Nonce, string Digest, long ExpiresUnixMs, string Decision);

internal sealed class ApprovalSession
{
    private readonly object gate = new();
    private readonly HashSet<string> used = new(StringComparer.Ordinal);
    private readonly ElapsedDeadline lease;
    private readonly DateTimeOffset expires;
    private bool revoked;
    private readonly CancellationTokenSource revokedSignal = new();
    internal CancellationToken RevocationToken => revokedSignal.Token;
    private string threadId, turnId;
    public string Id { get; }
    public string Task { get; }
    public string Project { get; }
    public string Scope { get; }

    // Construction follows explicit owner approval in the native UI. This
    // object alone does not establish an OS sandbox or permit launching a task.
    internal ApprovalSession(string task, string project, string scope, Func<DateTimeOffset> clock, TimeSpan lifetime, Func<ulong> elapsed = null)
    {
        if (string.IsNullOrWhiteSpace(task) || task.Length > 2048 || string.IsNullOrWhiteSpace(project) ||
            project.Length > 2048 || scope != "workspace-write; network-disabled" || lifetime <= TimeSpan.Zero || lifetime > TimeSpan.FromMinutes(5))
            throw new ArgumentException("Invalid approval context.");
        if (!DisplaySafe(task) || !DisplaySafe(project)) throw new ArgumentException("Unsafe display text.");
        if (!Path.IsPathFullyQualified(project)) throw new ArgumentException("A fully qualified project path is required.");
        Task = task; Project = Path.GetFullPath(project); Scope = scope;
        if (clock == null) throw new ArgumentNullException(nameof(clock));
        expires = clock().Add(lifetime); // Display/client hint only; never authority.
        lease = new ElapsedDeadline(lifetime, elapsed);
        Id = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
    }

    // Must be called only from a trusted native provider transport after a
    // verified thread/start and turn/start. Never bind from a worker message.
    internal bool BindTurn(string thread, string turn)
    {
        lock (gate)
        {
            if (revoked || lease.Remaining() == TimeSpan.Zero || threadId != null || string.IsNullOrWhiteSpace(thread) || string.IsNullOrWhiteSpace(turn) ||
                thread.Length > 128 || turn.Length > 128 || !DisplaySafe(thread) || !DisplaySafe(turn)) return false;
            threadId = thread; turnId = turn; return true;
        }
    }

    internal void Revoke()
    {
        lock (gate) revoked = true;
        revokedSignal.Cancel(); // Never hold the authority lock in callbacks.
    }
    internal TimeSpan AuthorityRemaining()
    {
        lock (gate) return revoked ? TimeSpan.Zero : lease.Remaining();
    }
    // Serialize provider delivery with revocation; no grant is sent after a
    // cancellation token has been set or session expiry/revocation is observed.
    internal bool CommitIfActive(CancellationToken cancellation, Action send)
    {
        lock (gate)
        {
            if (revoked || cancellation.IsCancellationRequested || lease.Remaining() == TimeSpan.Zero) return false;
            send(); return true;
        }
    }

    // `nativePrompt` must display the complete task, project, scope and payload
    // in a native host-owned dialog. It must return false on close/cancel.
    internal ApprovalResponse Decide(ApprovalRequest request, Func<ApprovalRequest, bool> nativePrompt)
    {
        bool valid;
        lock (gate)
        {
            valid = !revoked && lease.Remaining() > TimeSpan.Zero && request != null && request.Session == Id &&
                request.Task == Task && request.Project == Project && request.Scope == Scope &&
                request.Nonce is { Length: 32 } && request.Nonce.All(Uri.IsHexDigit) &&
                request.Payload is { Length: > 0 and <= 8192 } && DisplaySafe(request.Payload) && ValidProviderRequest(request.Payload) && request.Digest is { Length: 64 } &&
                CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(Digest(request.Payload)), Encoding.ASCII.GetBytes(request.Digest)) &&
                used.Count < 128 && used.Add(request.Nonce);
        }
        bool accepted = false;
        if (valid && nativePrompt != null)
        {
            try { accepted = nativePrompt(request); } catch { accepted = false; }
        }
        lock (gate)
        {
            accepted = accepted && !revoked && lease.Remaining() > TimeSpan.Zero;
            return new ApprovalResponse(request?.Session ?? "", request?.Nonce ?? "", request?.Digest ?? "", expires.ToUnixTimeMilliseconds(), accepted ? "accept" : "decline");
        }
    }

    private bool ValidProviderRequest(string payload)
    {
        if (threadId == null || turnId == null) return false;
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object || !UniqueProperties(root) || !root.TryGetProperty("id", out var id) ||
                !((id.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(id.GetString())) || (id.ValueKind == JsonValueKind.Number && id.TryGetInt64(out _))) ||
                !root.TryGetProperty("method", out var method) || method.ValueKind != JsonValueKind.String ||
                method.GetString() is not ("item/commandExecution/requestApproval" or "item/fileChange/requestApproval") ||
                !root.TryGetProperty("params", out var parameters) || parameters.ValueKind != JsonValueKind.Object ||
                !parameters.TryGetProperty("threadId", out var thread) || thread.ValueKind != JsonValueKind.String || thread.GetString() != threadId ||
                !parameters.TryGetProperty("turnId", out var turn) || turn.ValueKind != JsonValueKind.String || turn.GetString() != turnId) return false;
            return true;
        }
        catch (JsonException) { return false; }
    }

    private static bool UniqueProperties(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
                if (!names.Add(property.Name) || !UniqueProperties(property.Value)) return false;
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var item in value.EnumerateArray()) if (!UniqueProperties(item)) return false;
        return true;
    }

    internal static bool DisplaySafe(string value) => value != null && value.All(c => !char.IsControl(c) && CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.Format);

    private static string Digest(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
