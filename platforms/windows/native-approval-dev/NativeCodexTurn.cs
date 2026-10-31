// Development only: native process owns the provider pipe and binds turns.
// Not imported or called by the restricted preview. Never enable without native
// Windows sandbox, executable identity, project guard and cancellation review.
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Atlas.NativeApprovalDev;

internal sealed record NativeTurnResult(string Status, string Text, string TerminalStatus);

internal sealed class NativeCodexTurn
{
    private const int MaxEarly = 256;
    private readonly ApprovalSession session;
    private readonly WindowsProjectGuard project;
    private readonly CodexProcessChannel channel;
    private readonly string profile;
    private readonly Func<ulong> elapsed;
    private readonly List<JsonElement> early = new();
    private long sequence;
    private string threadId, turnId;
    private bool approvalDenied;
    private readonly Dictionary<string, string> providerRequests = new(StringComparer.Ordinal);

    internal NativeCodexTurn(ApprovalSession nativeOwnerApproved, WindowsProjectGuard lockedProject, CodexProcessChannel nativeProviderChannel, string requestedProfile, Func<ulong> elapsed = null)
    {
        session = nativeOwnerApproved ?? throw new ArgumentNullException(nameof(nativeOwnerApproved));
        project = lockedProject ?? throw new ArgumentNullException(nameof(lockedProject));
        channel = nativeProviderChannel ?? throw new ArgumentNullException(nameof(nativeProviderChannel));
        if (!Regex.IsMatch(requestedProfile ?? "", "^atlas_[a-f0-9]{32}$")) throw new ArgumentException("Invalid isolated permission profile.");
        if (!string.Equals(session.Project, project.Project, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Project does not match owner approval.");
        profile = requestedProfile;
        this.elapsed = elapsed;
    }

    // The trusted host must provide the vetted local executable path; no WebView
    // or model may choose it. Executable signature/version validation remains a
    // release prerequisite. The current restricted preview never calls this.
    internal static ProcessStartInfo CreateProviderStart(string executable, string profile)
    {
        if (!OperatingSystem.IsWindows() || !Path.IsPathFullyQualified(executable) || !File.Exists(executable) || !executable.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || !Regex.IsMatch(profile ?? "", "^atlas_[a-f0-9]{32}$")) throw new InvalidOperationException("Vetted native Codex executable required.");
        var info = new ProcessStartInfo(executable) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, CreateNoWindow = true, StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = new UTF8Encoding(false) };
        foreach (var a in new[] { "app-server", "--disable", "hooks", "--disable", "plugins", "--disable", "apps", "--disable", "skill_search", "--disable", "remote_plugin", "--disable", "skill_mcp_dependency_install", "--disable", "shell_snapshot" }) info.ArgumentList.Add(a);
        string permission = "permissions." + profile;
        foreach (var setting in new[] { permission + ".filesystem={\":minimal\"=\"read\",\":workspace_roots\"=\"write\"}", permission + ".network.enabled=false", "default_permissions=\"" + profile + "\"", "allow_login_shell=false", "shell_environment_policy.inherit=\"none\"", "shell_environment_policy.ignore_default_excludes=false", "web_search=\"disabled\"", "apps._default.enabled=false", "windows.sandbox=\"mxc\"" })
        { info.ArgumentList.Add("-c"); info.ArgumentList.Add(setting); }
        // Start from an allowlist, never from the parent's credential, proxy,
        // base-URL, SSH agent, or arbitrary executable-search environment.
        string system32 = Environment.SystemDirectory;
        string windows = Directory.GetParent(system32)?.FullName ?? throw new InvalidOperationException("Windows system directory unavailable.");
        string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (!Path.IsPathFullyQualified(system32) || !Path.IsPathFullyQualified(windows) || !Path.IsPathFullyQualified(userProfile)) throw new InvalidOperationException("Required platform paths unavailable.");
        info.Environment.Clear();
        info.Environment["SystemRoot"] = windows;
        info.Environment["WINDIR"] = windows;
        info.Environment["PATH"] = system32;
        info.Environment["USERPROFILE"] = userProfile; // Default existing account location; no credential material is copied.
        foreach (var pair in new[] { ("LOCALAPPDATA", Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)), ("APPDATA", Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData)), ("TEMP", Path.GetTempPath()), ("TMP", Path.GetTempPath()) })
        {
            if (string.IsNullOrWhiteSpace(pair.Item2) || !Path.IsPathFullyQualified(pair.Item2)) throw new InvalidOperationException("Required platform path unavailable.");
            info.Environment[pair.Item1] = pair.Item2;
        }
        return info;
    }

    private static JsonElement Required(JsonElement parent, string name, JsonValueKind kind)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var value) || value.ValueKind != kind) throw new InvalidDataException("Provider response failed verification.");
        return value;
    }
    private static bool NullOrMissing(JsonElement obj, string name) => !obj.TryGetProperty(name, out var v) || v.ValueKind == JsonValueKind.Null;
    private static string RequiredString(JsonElement parent, string name) => Required(parent, name, JsonValueKind.String).GetString()!;
    private static bool IsFalse(JsonElement obj, string name) => obj.ValueKind == JsonValueKind.Object && obj.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.False;
    private static bool IsEmpty(JsonElement value) => value.ValueKind == JsonValueKind.Null || value.ValueKind == JsonValueKind.False || (value.ValueKind == JsonValueKind.Object && !value.EnumerateObject().Any()) || (value.ValueKind == JsonValueKind.Array && value.GetArrayLength() == 0);
    private static void Require(bool condition) { if (!condition) throw new InvalidDataException("Provider configuration or scope was not verified."); }

    internal static TimeSpan DispatchAuthority(ApprovalSession authority, WindowsProjectGuard projectGuard)
    {
        // Filesystem checks run on the writer outside the session authority lock.
        projectGuard.EnsureActive();
        return authority.AuthorityRemaining();
    }

    private async Task<JsonElement> RequestAsync(string method, object parameters, CancellationToken cancellation, bool captureEarly = false)
    {
        project.EnsureActive(); cancellation.ThrowIfCancellationRequested();
        long id = Interlocked.Increment(ref sequence);
        var frame = new { id, method, @params = parameters };
        if (method is "thread/start" or "turn/start")
        {
            if (!session.CommitIfActive(cancellation, () => channel.Send(frame, cancellation, session.RevocationToken, () => DispatchAuthority(session, project)))) throw new OperationCanceledException();
        }
        else channel.Send(frame);
        var deadline = new ElapsedDeadline(TimeSpan.FromSeconds(30), elapsed);
        while (true)
        {
            var remaining = deadline.Remaining(); if (remaining <= TimeSpan.Zero) throw new TimeoutException("Provider request timed out.");
            // Windows waits can exclude sleep: poll so elapsed time is checked
            // promptly after wake rather than trusting a single long wait.
            if (remaining > TimeSpan.FromMilliseconds(250)) remaining = TimeSpan.FromMilliseconds(250);
            JsonElement message;
            try { message = await channel.ReceiveAsync(remaining, cancellation); }
            catch (OperationCanceledException) when (!cancellation.IsCancellationRequested) { continue; }
            if (message.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Invalid provider message.");
            if (message.TryGetProperty("method", out _))
            {
                if (message.TryGetProperty("id", out _)) { Reject(message); throw new InvalidDataException("Provider requested an action before turn verification."); }
                if (captureEarly) { if (early.Count >= MaxEarly) throw new InvalidDataException("Too many early provider events."); early.Add(message); }
                continue;
            }
            if (!message.TryGetProperty("id", out var responseId) || responseId.ValueKind != JsonValueKind.Number || !responseId.TryGetInt64(out long actual) || actual != id) continue;
            if (message.TryGetProperty("error", out _)) throw new InvalidDataException("Provider rejected a request.");
            return Required(message, "result", JsonValueKind.Object);
        }
    }
    private void Reject(JsonElement message)
    {
        if (!message.TryGetProperty("id", out var id) || id.ValueKind is not (JsonValueKind.String or JsonValueKind.Number)) throw new InvalidDataException("Invalid provider request ID.");
        channel.Send(new { id = id.Clone(), error = new { code = -32601, message = "Unsupported request; no permission granted." } });
        approvalDenied = true;
    }
    private async Task<string> PreflightAsync(CancellationToken cancellation)
    {
        var config = Required(await RequestAsync("config/read", new { cwd = project.Project, includeLayers = false }, cancellation), "config", JsonValueKind.Object);
        // Explicit MXC must not silently fall back to a weaker implementation.
        // This configuration echo is not proof of OS enforcement.
        Require(RequiredString(Required(config, "windows", JsonValueKind.Object), "sandbox") == "mxc");
        Require(!Required(config, "mcp_servers", JsonValueKind.Object).EnumerateObject().Any());
        var inventory = await RequestAsync("mcpServerStatus/list", new { detail = "toolsAndAuthOnly", limit = 100 }, cancellation);
        Require(Required(inventory, "data", JsonValueKind.Array).GetArrayLength() == 0 && NullOrMissing(inventory, "nextCursor"));
        var apps = Required(config, "apps", JsonValueKind.Object);
        Require(IsFalse(Required(apps, "_default", JsonValueKind.Object), "enabled"));
        foreach (var app in apps.EnumerateObject()) if (app.Name != "_default") Require(app.Value.ValueKind == JsonValueKind.Object && (!app.Value.TryGetProperty("enabled", out var enabled) || enabled.ValueKind is JsonValueKind.Null or JsonValueKind.False));
        Require(RequiredString(config, "default_permissions") == profile);
        var permission = Required(Required(config, "permissions", JsonValueKind.Object), profile, JsonValueKind.Object);
        Require(NullOrMissing(permission, "extends") && NullOrMissing(permission, "workspace_roots"));
        var fs = Required(permission, "filesystem", JsonValueKind.Object);
        Require(RequiredString(fs, ":minimal") == "read" && RequiredString(fs, ":workspace_roots") == "write");
        Require(fs.EnumerateObject().All(p => p.Name is ":minimal" or ":workspace_roots" or "glob_scan_max_depth"));
        var network = Required(permission, "network", JsonValueKind.Object);
        Require(IsFalse(network, "enabled") && network.EnumerateObject().All(p => p.Name == "enabled" || IsEmpty(p.Value)));
        var features = Required(config, "features", JsonValueKind.Object);
        foreach (var name in new[] { "hooks", "plugins", "apps", "skill_search", "remote_plugin", "skill_mcp_dependency_install", "shell_snapshot" }) Require(IsFalse(features, name));
        Require(RequiredString(config, "web_search") == "disabled" && IsFalse(config, "allow_login_shell"));
        var shell = Required(config, "shell_environment_policy", JsonValueKind.Object);
        Require(RequiredString(shell, "inherit") == "none" && IsFalse(shell, "ignore_default_excludes"));
        foreach (string field in new[] { "hooks", "skills" })
        {
            object args = field == "skills" ? new { cwds = new[] { project.Project }, forceReload = true } : new { cwds = new[] { project.Project } };
            var result = await RequestAsync(field + "/list", args, cancellation);
            var rows = Required(result, "data", JsonValueKind.Array); Require(rows.GetArrayLength() > 0);
            foreach (var row in rows.EnumerateArray())
            {
                if (row.TryGetProperty("errors", out var errors)) Require(errors.ValueKind == JsonValueKind.Array && errors.GetArrayLength() == 0);
                var entries = Required(row, field, JsonValueKind.Array);
                foreach (var item in entries.EnumerateArray()) Require(field == "skills" && item.ValueKind == JsonValueKind.Object && IsFalse(item, "enabled"));
            }
        }
        var account = Required(await RequestAsync("account/read", new { refreshToken = false }, cancellation), "account", JsonValueKind.Object);
        Require(RequiredString(account, "type") == "chatgpt");
        var listing = await RequestAsync("model/list", new { includeHidden = false, limit = 100 }, cancellation);
        Require(NullOrMissing(listing, "nextCursor"));
        var candidates = Required(listing, "data", JsonValueKind.Array).EnumerateArray().Where(m => m.ValueKind == JsonValueKind.Object && m.TryGetProperty("isDefault", out var d) && d.ValueKind == JsonValueKind.True && (!m.TryGetProperty("hidden", out var hidden) || hidden.ValueKind is JsonValueKind.False or JsonValueKind.Null)).ToArray();
        Require(candidates.Length == 1);
        string model = RequiredString(candidates[0], "model"); Require(Regex.IsMatch(model, "^[A-Za-z0-9._-]{1,128}$"));
        return model;
    }

    // This entry point is intentionally not wired to the app. Only a native host
    // that has shown its own task dialog may construct the session and channel.
    internal async Task<NativeTurnResult> RunAsync(Func<ApprovalRequest, bool> nativePrompt, CancellationToken requestedStop)
    {
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(requestedStop);
        limit.CancelAfter(TimeSpan.FromMinutes(5));
        using var registration = limit.Token.Register(session.Revoke);
        var text = new StringBuilder();
        try
        {
            await RequestAsync("initialize", new { clientInfo = new { name = "atlas-native-dev", version = "0.1" }, capabilities = new { experimentalApi = true } }, limit.Token);
            channel.Send(new { method = "initialized", @params = new { } });
            string model = await PreflightAsync(limit.Token);
            var started = await RequestAsync("thread/start", new { cwd = project.Project, runtimeWorkspaceRoots = new[] { project.Project }, permissions = profile, approvalPolicy = "on-request", approvalsReviewer = "user", model }, limit.Token);
            Require(RequiredString(Required(started, "activePermissionProfile", JsonValueKind.Object), "id") == profile);
            var roots = Required(started, "runtimeWorkspaceRoots", JsonValueKind.Array);
            Require(roots.GetArrayLength() == 1 && roots[0].ValueKind == JsonValueKind.String && string.Equals(roots[0].GetString(), project.Project, StringComparison.OrdinalIgnoreCase));
            Require(RequiredString(started, "approvalPolicy") == "on-request" && RequiredString(started, "approvalsReviewer") == "user");
            var thread = Required(started, "thread", JsonValueKind.Object);
            Require(RequiredString(thread, "model") == model);
            threadId = RequiredString(thread, "id");
            var turn = await RequestAsync("turn/start", new { threadId, input = new[] { new { type = "text", text = session.Task, text_elements = Array.Empty<object>() } } }, limit.Token, true);
            turnId = RequiredString(Required(turn, "turn", JsonValueKind.Object), "id");
            Require(session.BindTurn(threadId, turnId));
            foreach (var item in early)
            {
                var terminal = Handle(item, nativePrompt, limit.Token, text);
                if (terminal != null) return terminal;
            }
            early.Clear();
            while (true)
            {
                project.EnsureActive();
                var item = await channel.ReceiveAsync(TimeSpan.FromMinutes(5), limit.Token);
                var terminal = Handle(item, nativePrompt, limit.Token, text);
                if (terminal != null) return terminal;
            }
        }
        catch (OperationCanceledException)
        {
            // Acknowledgement is bounded; loss of the provider or a timeout is
            // unknown, never interpreted as proof that actions were undone.
            string status = "unknown";
            if (threadId != null && turnId != null)
            {
                try
                {
                    channel.Send(new { id = Interlocked.Increment(ref sequence), method = "turn/interrupt", @params = new { threadId, turnId } });
                    using var grace = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                    while (true)
                    {
                        var item = await channel.ReceiveAsync(TimeSpan.FromSeconds(5), grace.Token);
                        if (item.TryGetProperty("id", out _) && item.TryGetProperty("method", out _)) { Reject(item); continue; }
                        if (Terminal(item, out string observed)) { status = observed; break; }
                    }
                }
                catch (Exception ex) when (ex is OperationCanceledException or IOException or InvalidDataException or ObjectDisposedException) { }
            }
            return new NativeTurnResult("stopped; partial changes may remain", text.ToString(), status);
        }
        finally { session.Revoke(); }
    }

    private bool Terminal(JsonElement item, out string status)
    {
        status = null;
        if (item.ValueKind != JsonValueKind.Object || !item.TryGetProperty("method", out var method) || method.ValueKind != JsonValueKind.String || method.GetString() != "turn/completed" ||
            !item.TryGetProperty("params", out var p) || p.ValueKind != JsonValueKind.Object || !p.TryGetProperty("threadId", out var t) || t.ValueKind != JsonValueKind.String || t.GetString() != threadId ||
            !p.TryGetProperty("turn", out var turn) || turn.ValueKind != JsonValueKind.Object || !turn.TryGetProperty("id", out var id) || id.ValueKind != JsonValueKind.String || id.GetString() != turnId ||
            !turn.TryGetProperty("status", out var s) || s.ValueKind != JsonValueKind.String || s.GetString() is not ("completed" or "interrupted" or "failed")) return false;
        status = s.GetString(); return true;
    }

    private NativeTurnResult Handle(JsonElement item, Func<ApprovalRequest, bool> nativePrompt, CancellationToken stop, StringBuilder text)
    {
        stop.ThrowIfCancellationRequested();
        if (item.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Invalid provider message.");
        if (item.TryGetProperty("method", out var method) && item.TryGetProperty("id", out var id))
        {
            if (method.ValueKind != JsonValueKind.String || id.ValueKind is not (JsonValueKind.String or JsonValueKind.Number)) throw new InvalidDataException("Invalid provider request.");
            // Provider RPC identity, not a fresh UI nonce, determines whether
            // this request has already been seen. Never repeat a prompt or a
            // grant for an identical or conflicting reuse of an ID.
            string rpcId;
            if (id.ValueKind == JsonValueKind.String && id.GetString() is { Length: > 0 and <= 256 } textId) rpcId = "s:" + textId;
            else if (id.ValueKind == JsonValueKind.Number && id.TryGetInt64(out long numberId)) rpcId = "n:" + numberId.ToString(System.Globalization.CultureInfo.InvariantCulture);
            else throw new InvalidDataException("Invalid provider request identity.");
            string payload = item.GetRawText();
            string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(payload))).ToLowerInvariant();
            if (providerRequests.TryGetValue(rpcId, out string previous))
            {
                session.Revoke();
                throw new InvalidDataException(previous == digest ? "Duplicate provider request." : "Conflicting provider request identity.");
            }
            if (providerRequests.Count >= 128) { session.Revoke(); throw new InvalidDataException("Too many provider requests."); }
            providerRequests.Add(rpcId, digest);
            var request = new ApprovalRequest(session.Id, Convert.ToHexString(RandomNumberGenerator.GetBytes(16)).ToLowerInvariant(), session.Task, session.Project, session.Scope, payload, digest);
            var decision = session.Decide(request, nativePrompt);
            if (decision.Decision != "accept") approvalDenied = true;
            project.EnsureActive();
            if (!session.CommitIfActive(stop, () => channel.Send(new { id = id.Clone(), result = new { decision = decision.Decision } }, stop, session.RevocationToken, () => DispatchAuthority(session, project)))) throw new OperationCanceledException();
            return null;
        }
        if (Terminal(item, out string status)) return new NativeTurnResult(approvalDenied ? "approval denied" : status, text.ToString(), status);
        if (method.ValueKind == JsonValueKind.String && method.GetString() == "item/agentMessage/delta" && item.TryGetProperty("params", out var p) && p.ValueKind == JsonValueKind.Object &&
            p.TryGetProperty("threadId", out var t) && t.ValueKind == JsonValueKind.String && t.GetString() == threadId && p.TryGetProperty("turnId", out var n) && n.ValueKind == JsonValueKind.String && n.GetString() == turnId && p.TryGetProperty("delta", out var delta) && delta.ValueKind == JsonValueKind.String)
        {
            string fragment = delta.GetString(); if (text.Length + fragment.Length > 1_048_576) throw new InvalidDataException("Provider output too long."); text.Append(fragment);
        }
        return null;
    }
}
