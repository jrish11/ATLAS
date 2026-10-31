// Partial package verifier; development only. Not a complete trust boundary.
using System.Text.Json;

namespace Atlas.NativeApprovalDev;

internal sealed class VerifiedCodexPackage : IDisposable
{
    internal const string ManifestSha256 = "b035b02d5cc8f913648a71b00df181c91a83b99753f5a0302f05e99fb485081f";
    private static readonly (string Path, string Hash)[] Required = {
        ("bin/codex.exe", "9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42"),
        ("bin/codex-code-mode-host.exe", "977c1f01c9efac0bfe1b9032717c95f92e1c965c8441a8dacbfe824c5c79a527"),
        ("bin/codex-exec-server.exe", "eda5263b31e0354347e7bcdc434aff82f5c630ddba69f13449742a64e1836a37"),
        ("codex-path/rg.exe", "14231169855ec5205cf5a1b6f1db358ff4aed4247c86b69ce8aae647c77f6680"),
        ("codex-resources/codex-command-runner.exe", "5e68e3f5b4640af55db2873a0d0dc038907145708f9e735870d9279a8074c2df"),
        ("codex-resources/codex-windows-sandbox-setup.exe", "3995c4f57199eb8023a0f3a585f6e9fdc4d5174c22a51837aaeb15beb52954f0")
    };
    private readonly List<FileStream> held = new();
    internal string Executable { get; private set; }
    private VerifiedCodexPackage() { }
    private static void CheckAncestors(string path)
    {
        string current = Path.GetFullPath(path);
        while (!string.IsNullOrEmpty(current))
        {
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new InvalidOperationException("Package reparse points are not allowed.");
            var parent = Directory.GetParent(current);
            if (parent == null) break;
            current = parent.FullName;
        }
    }
    internal static VerifiedCodexPackage Open(string root)
    {
        if (!OperatingSystem.IsWindows() || !Path.IsPathFullyQualified(root)) throw new InvalidOperationException("An absolute Windows package directory is required.");
        root = Path.GetFullPath(root); CheckAncestors(root);
        var result = new VerifiedCodexPackage();
        try
        {
            string manifestPath = Path.Combine(root, "codex-package.json"); CheckAncestors(manifestPath);
            var manifest = new FileStream(manifestPath, FileMode.Open, FileAccess.Read, FileShare.Read); result.held.Add(manifest);
            if (manifest.Length != 261 || !PinnedCodexExecutable.MatchesDigest(manifest, ManifestSha256)) throw new InvalidDataException("Official package manifest bytes do not match the pinned release.");
            manifest.Position = 0;
            using (var json = JsonDocument.Parse(manifest))
            {
                var obj = json.RootElement;
                if (obj.GetProperty("version").GetString() != "0.166.0" || obj.GetProperty("target").GetString() != "x86_64-pc-windows-msvc" || obj.GetProperty("entrypoint").GetString() != "bin/codex.exe" || obj.GetProperty("resourcesDir").GetString() != "codex-resources") throw new InvalidDataException("Unexpected official package manifest.");
            }
            foreach (var item in Required)
            {
                string path = Path.Combine(root, item.Path.Replace('/', Path.DirectorySeparatorChar)); CheckAncestors(path);
                var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read); result.held.Add(file);
                if (!PinnedCodexExecutable.MatchesDigest(file, item.Hash)) throw new InvalidDataException("Package file digest mismatch: " + item.Path);
                if (item.Path == "bin/codex.exe") result.Executable = path;
            }
            return result;
        }
        catch { result.Dispose(); throw; }
    }
    public void Dispose() { foreach (var file in held) file.Dispose(); held.Clear(); }
}
