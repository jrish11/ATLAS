// Partial package verifier; development only. Not a complete trust boundary.
using System.Text.Json;

namespace Atlas.NativeApprovalDev;

internal sealed class VerifiedCodexPackage : IDisposable
{
    internal const string ManifestSha256 = "b035b02d5cc8f913648a71b00df181c91a83b99753f5a0302f05e99fb485081f";
    // Exact archive members from the independently verified official tarball.
    private static readonly (string Path, string Hash)[] Required = {
        ("bin/codex-code-mode-host.exe", "977c1f01c9efac0bfe1b9032717c95f92e1c965c8441a8dacbfe824c5c79a527"),
        ("bin/codex-exec-server.exe", "eda5263b31e0354347e7bcdc434aff82f5c630ddba69f13449742a64e1836a37"),
        ("bin/codex.exe", "9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42"),
        ("codex-path/rg.exe", "14231169855ec5205cf5a1b6f1db358ff4aed4247c86b69ce8aae647c77f6680"),
        ("codex-resources/codex-command-runner.exe", "5e68e3f5b4640af55db2873a0d0dc038907145708f9e735870d9279a8074c2df"),
        ("codex-resources/codex-windows-sandbox-setup.exe", "3995c4f57199eb8023a0f3a585f6e9fdc4d5174c22a51837aaeb15beb52954f0"),
        ("codex-resources/voice/NOTICE.md", "473fcf8ccb68ce726111d016d133f0555adba730d057591512f3f71fb46aeb6e"),
        ("codex-resources/voice/bin/codex-voice-host.exe", "1d04e4f7fedf1cd028b14ad961d7cecbf138096d7397760d5eac98517016cd50"),
        ("codex-resources/voice/bin/gio-2.0-0.dll", "48e22ffbb076a07719f315c9fdc994516e7769b008e445931e042ba3b96621cb"),
        ("codex-resources/voice/bin/glib-2.0-0.dll", "1adcbaa2b3d5ea6b3f1b91f6616cea3240be7f8cb84f66d049649012ff0a51a4"),
        ("codex-resources/voice/bin/gmodule-2.0-0.dll", "292b716fb374e1f8074e0f9783500589f290bb23b111df150595539fb2d811f7"),
        ("codex-resources/voice/bin/gobject-2.0-0.dll", "4bf15d904d5aac573d6f3228cb1437e1785d9d67a566ef44407b8c1f25dc19f6"),
        ("codex-resources/voice/bin/gstapp-1.0-0.dll", "19b0a4ec4245b248325692a8fd4bdd65aa258b82ddd4b3c5de984d37f35cae9b"),
        ("codex-resources/voice/bin/gstapp.dll", "f7d87164108b44d76046f044149b7e2e6203dd1f27c3f3b080e89d293ccf4e60"),
        ("codex-resources/voice/bin/gstaudio-1.0-0.dll", "c25714472ae94ac3471847f437af77e78a7305d8a89cc2830385e960d27a0a4c"),
        ("codex-resources/voice/bin/gstaudioconvert.dll", "d9998e08c27d81431f64b1dd4f0d3406bbb4f49c6ca04574694f951feb6f65e7"),
        ("codex-resources/voice/bin/gstaudioresample.dll", "673ab7eff4836df8601a1f234a9af6aaa1de408eed3c384306e70ea18c2ab855"),
        ("codex-resources/voice/bin/gstbase-1.0-0.dll", "fb5877dcd5c8e07b617b6c619f6133ef6843ae4af76b3c9affa44d8e5ce04fa7"),
        ("codex-resources/voice/bin/gstcoreelements.dll", "c7948573d7ed5e29d99884682ab9169beb7e5c4e695b7302af8aeff9f45d2f90"),
        ("codex-resources/voice/bin/gstnet-1.0-0.dll", "c63055fddc304f72dd1fe1ace67185ad55edbc0b114c1bf2c028148674e34b27"),
        ("codex-resources/voice/bin/gstopus.dll", "dbde5b23defeeddc3b5118ac053ae2cb590d9e5c3c9b01dc05a73665588bda55"),
        ("codex-resources/voice/bin/gstpbutils-1.0-0.dll", "95d0bcefeca177697c8667ae9854cadf11b55f895dcbb79fb4113cb072999c51"),
        ("codex-resources/voice/bin/gstreamer-1.0-0.dll", "c9b95737515307317d60807cbce4d2991fb57ef683953f6f90ebe9da056a76ed"),
        ("codex-resources/voice/bin/gstrtp-1.0-0.dll", "ca99fe474bc4d2f91bfe85a03c110f2645bd5f239a1e34d5c77c7fd6fe5163a0"),
        ("codex-resources/voice/bin/gstrtp.dll", "c52acb6d4e963797d84c0f9f74a155abbb4c2aa07c04643626b67161185fedd9"),
        ("codex-resources/voice/bin/gstrtpmanager.dll", "64b49ede3bf2df019cc508b88ce907fb5a81dc298d8a7fa0234e7bf14b8209c8"),
        ("codex-resources/voice/bin/gsttag-1.0-0.dll", "96b59dc2b5b123afe52b89b28be026faa6e964feeba3ec7af2a3acb7c6a7a002"),
        ("codex-resources/voice/bin/gstvideo-1.0-0.dll", "106d93d9f85e7d7f8a3379a6cc677cd476e24c40557de5707ad612699e8a9e2d"),
        ("codex-resources/voice/bin/intl-8.dll", "227f319a16fcd112ea7f96ca6bd77621ad83357b23af19f6cbbf42a9e802c70f"),
        ("codex-resources/voice/bin/libffi-8.dll", "b671685958738ad2fcd602075a296758f7e76f34da108dbd98503ea1698fc9bf"),
        ("codex-resources/voice/bin/opus.dll", "59281bf42c10174313bb777b858723cb3036871bba763b45b36db73fae522260"),
        ("codex-resources/voice/bin/pcre2-8.dll", "57d2c0d73096f5151e47c08848420bf9d1bada50135a34eb13befd93062fbe29"),
        ("codex-resources/voice/bin/vcruntime140.dll", "184146852727a9db4eea06178716bec3cdbb1015c911f6b0f915b184ad7775b2"),
        ("codex-resources/voice/bin/z.dll", "278186f4c34713f3e29d11e2f0d67adaf46e9de91b7ebe3532a963650ae23ba5"),
        ("codex-resources/voice/licenses/LGPL-2.1.txt", "c7ce1276717604c29c5469179a2f368eac42846557be671bb52f4e16e884b2ad"),
        ("codex-resources/voice/licenses/Opus.txt", "cbd8bd07329a234413710c02b19d22c0cf78fc451882593e817130779b5455e3"),
        ("codex-resources/voice/licenses/PCRE2.md", "4195c519dcfe4a4ffedc4b8ccc5d49e4dd02efd5ece6b69a4fba5d20080902a9"),
        ("codex-resources/voice/licenses/libffi.txt", "e2a9b884b1c5d718efd6121457a1fbe7ece431352ca75c901260cef2e7d040e5"),
        ("codex-resources/voice/licenses/proxy-libintl.txt", "aa092600e3f475f0a55821fb9c529583d8e23e41bf0461254f02fcf94d3a32c2"),
        ("codex-resources/voice/licenses/sljit.txt", "37c7a090fc61388430d63fc97bf8a22ffce92d3ca2249aac572cfaf411d3070f"),
        ("codex-resources/voice/licenses/zlib.txt", "439c75ab12b340c5362b9d4b08ff05ec3a4d0eb7667a6fff49a9b16d8795c78e"),
        ("codex-resources/voice/manifest.json", "7c19df93126891145b3b2f63026aa4c2e128b4f18114d3979903f1b6e327a583"),
        ("codex-resources/voice/runtime.json", "be48cbdc1fe91f128fe97baec26cff2ebd90ef7f477ae18407ce16ebb3754643"),
        ("codex-resources/voice/sources.json", "e2f6b124f6277e7c3c4f5c7cc8830c66190f671ad65e972bb2cc9507dbfcb937"),
        ("codex-resources/voice/windows-crt.json", "d16939bc85da395ded5411724fed84ffd36810b78d47c756cf094b0956bc3892")
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
    // This is an inventory check, not a substitute for holding directory identities.
    internal static void CheckInventory(IEnumerable<string> names)
    {
        var expected = new HashSet<string>(Required.Select(x => x.Path), StringComparer.OrdinalIgnoreCase) { "codex-package.json" };
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string name in names)
            if (!expected.Contains(name) || !seen.Add(name)) throw new InvalidDataException("Unexpected or duplicate package file: " + name);
        if (!seen.SetEquals(expected)) throw new InvalidDataException("Package files missing.");
    }
    private static IEnumerable<string> Inventory(string root)
    {
        var pending = new Stack<string>(); pending.Push(root);
        while (pending.Count != 0)
        {
            string directory = pending.Pop();
            foreach (string path in Directory.EnumerateFileSystemEntries(directory))
            {
                var attributes = File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("Package reparse point denied.");
                if ((attributes & FileAttributes.Directory) != 0) pending.Push(path);
                else yield return Path.GetRelativePath(root, path).Replace('\\', '/');
            }
        }
    }
    internal static VerifiedCodexPackage Open(string root)
    {
        if (!OperatingSystem.IsWindows() || !Path.IsPathFullyQualified(root)) throw new InvalidOperationException("An absolute Windows package directory is required.");
        root = Path.GetFullPath(root); CheckAncestors(root);
        var result = new VerifiedCodexPackage();
        try
        {
            CheckInventory(Inventory(root));
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
