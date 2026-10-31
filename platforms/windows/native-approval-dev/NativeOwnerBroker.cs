// Unwired development broker. The restricted release never compiles or calls it.
// The false gate is intentional: digest alone is not a sandbox or complete
// executable/helper provenance; process containment and OS checks remain open.
using System.Security.Cryptography;
using System.Windows.Forms;

namespace Atlas.NativeApprovalDev;

internal sealed class PinnedCodexExecutable : IDisposable
{
    // Official OpenAI rust-v0.166.0 GitHub release, standalone x64 Windows EXE.
    // https://github.com/openai/codex/releases/expanded_assets/rust-v0.166.0
    internal const string ExpectedSha256 = "9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42";
    private readonly FileStream held;
    internal string Path { get; }
    private PinnedCodexExecutable(string path, FileStream stream) { Path = path; held = stream; }
    internal static bool MatchesDigest(Stream data, string expected)
    {
        if (expected == null || expected.Length != 64) return false;
        byte[] expectedBytes;
        try { expectedBytes = Convert.FromHexString(expected); } catch (FormatException) { return false; }
        return CryptographicOperations.FixedTimeEquals(SHA256.HashData(data), expectedBytes);
    }
    internal static PinnedCodexExecutable Open(string path)
    {
        if (!OperatingSystem.IsWindows() || !System.IO.Path.IsPathFullyQualified(path) || !path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidOperationException("A supported pinned Codex executable is required.");
        var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        try
        {
            if (!MatchesDigest(stream, ExpectedSha256) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("Codex executable did not match the reviewed official release.");
            return new PinnedCodexExecutable(System.IO.Path.GetFullPath(path), stream);
        }
        catch { stream.Dispose(); throw; }
    }
    public void Dispose() => held.Dispose();
}

internal static class NativeOwnerBroker
{
    // Immutable gate: no settings, environment, WebView messages or user input
    // can switch this on. Remove only after independent native/security review.
    internal static bool Enabled => false;

    internal static async Task<NativeTurnResult> RunAsync(Control owner, string task, string selectedProject, string codexExecutable, CancellationToken stop)
    {
        if (!Enabled) throw new InvalidOperationException("Windows native AI broker is not enabled.");
        if (owner == null || owner.IsDisposed || owner.InvokeRequired) throw new InvalidOperationException("A live native UI owner on its UI thread is required.");
        using var project = WindowsProjectGuard.Open(selectedProject);
        var approval = NativeApprovalDialog.ConfirmTask(owner, task, project.Project);
        if (approval == null) return new NativeTurnResult("declined", "", "not started");
        try
        {
            stop.ThrowIfCancellationRequested();
            string bin = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(codexExecutable));
            if (!string.Equals(System.IO.Path.GetFileName(codexExecutable), "codex.exe", StringComparison.OrdinalIgnoreCase) || !string.Equals(System.IO.Path.GetFileName(bin), "bin", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("An official package entrypoint is required.");
            using var package = VerifiedCodexPackage.Open(System.IO.Directory.GetParent(bin)?.FullName ?? throw new InvalidOperationException("Package root unavailable."));
            using var cli = PinnedCodexExecutable.Open(package.Executable);
            string profile = "atlas_" + Guid.NewGuid().ToString("N");
            using var channel = new CodexProcessChannel(NativeCodexTurn.CreateProviderStart(cli.Path, profile));
            var turn = new NativeCodexTurn(approval, project, channel, profile);
            return await turn.RunAsync(request =>
            {
                if (stop.IsCancellationRequested || owner.IsDisposed) return false;
                if (owner.InvokeRequired) return (bool)owner.Invoke(new Func<bool>(() => !stop.IsCancellationRequested && !owner.IsDisposed && NativeApprovalDialog.ConfirmAction(owner, request)));
                return NativeApprovalDialog.ConfirmAction(owner, request);
            }, stop);
        }
        finally { approval.Revoke(); }
    }
}
