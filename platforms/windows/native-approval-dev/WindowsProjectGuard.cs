// Development-only Windows project identity guard. Not wired to the preview.
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Atlas.NativeApprovalDev;

internal sealed class WindowsProjectGuard : IDisposable
{
    private const uint ShareRead = 1, ShareWrite = 2, OpenExisting = 3, BackupSemantics = 0x02000000, OpenReparsePoint = 0x00200000, Reparse = 0x400, DirectoryAttribute = 0x10;
    private sealed record Held(string Path, string Canonical, uint Volume, uint High, uint Low, SafeFileHandle Handle);
    private readonly List<Held> held = new();
    internal string Project { get; }
    private bool disposed;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileInfoNative
    {
        public uint Attributes; public System.Runtime.InteropServices.ComTypes.FILETIME Creation, Access, Write;
        public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    private static extern uint GetLongPathNameW(string input, StringBuilder output, uint capacity);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInfoNative info);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder path, uint size, uint flags);

    private WindowsProjectGuard(string project) => Project = project;
    private static SafeFileHandle OpenHandle(string path)
    {
        var h = CreateFileW(path, 0, ShareRead | ShareWrite, IntPtr.Zero, OpenExisting, BackupSemantics | OpenReparsePoint, IntPtr.Zero);
        if (h.IsInvalid) { int error = Marshal.GetLastWin32Error(); h.Dispose(); throw new Win32Exception(error); }
        return h;
    }
    private static FileInfoNative Identity(SafeFileHandle h)
    {
        if (!GetFileInformationByHandle(h, out var info) || (info.Attributes & Reparse) != 0 || (info.Attributes & DirectoryAttribute) == 0)
            throw new InvalidOperationException("Project identity or reparse status could not be verified.");
        return info;
    }
    private static string FinalPath(SafeFileHandle h)
    {
        var result = new StringBuilder(32768);
        uint length = GetFinalPathNameByHandleW(h, result, (uint)result.Capacity, 0);
        if (length == 0 || length >= result.Capacity) throw new InvalidOperationException("Canonical project path unavailable.");
        string path = result.ToString();
        if (!path.StartsWith(@"\\?\", StringComparison.Ordinal) || path.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Local canonical path required.");
        return Path.TrimEndingDirectorySeparator(path.Substring(4));
    }
    private static bool Same(string a, string b) => string.Equals(Path.TrimEndingDirectorySeparator(a), Path.TrimEndingDirectorySeparator(b), StringComparison.OrdinalIgnoreCase);
    private static bool Overlaps(string a, string b) => Same(a, b) || a.StartsWith(Path.TrimEndingDirectorySeparator(b) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || b.StartsWith(Path.TrimEndingDirectorySeparator(a) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);

    // Resolve the existing ancestor of every protected path through a handle,
    // retaining any missing suffix. Fail closed when identity cannot be read.
    private static string CanonicalProtected(string value)
    {
        string full = Path.TrimEndingDirectorySeparator(Path.GetFullPath(value));
        string current = full; var missing = new Stack<string>();
        while (!Directory.Exists(current))
        {
            string parent = Directory.GetParent(current)?.FullName ?? throw new InvalidOperationException("Protected path cannot be resolved.");
            missing.Push(Path.GetFileName(current)); current = parent;
        }
        using var handle = OpenHandle(current);
        Identity(handle);
        string canonical = FinalPath(handle);
        while (missing.Count != 0) canonical = Path.Combine(canonical, missing.Pop());
        return Path.TrimEndingDirectorySeparator(canonical);
    }
    internal static WindowsProjectGuard Open(string selected)
    {
        if (!OperatingSystem.IsWindows() || string.IsNullOrWhiteSpace(selected) || !Path.IsPathFullyQualified(selected)) throw new InvalidOperationException("A local Windows project is required.");
        // Win32 may silently strip trailing dots/spaces before a handle is
        // opened; reject those spellings before any lexical normalization.
        foreach (string segment in selected.Substring(Path.GetPathRoot(selected)!.Length).Split(new[] { '\\', '/' }, StringSplitOptions.RemoveEmptyEntries))
            if (segment.EndsWith(".", StringComparison.Ordinal) || segment.EndsWith(" ", StringComparison.Ordinal)) throw new InvalidOperationException("Ambiguous project path spelling.");
        // Compare the owner's spelling before GetFullPath can expand 8.3
        // aliases. The handle checks below still independently reject reparse
        // points and preserve the directory identity.
        var expanded = new StringBuilder(32768);
        uint expandedLength = GetLongPathNameW(selected, expanded, (uint)expanded.Capacity);
        if (expandedLength == 0 || expandedLength >= expanded.Capacity || !Same(selected.Replace('/', '\\'), expanded.ToString()))
            throw new InvalidOperationException("Short or ambiguous project path spelling is not accepted.");
        string project = Path.TrimEndingDirectorySeparator(Path.GetFullPath(selected));
        string root = Path.GetPathRoot(project)!;
        if (root.StartsWith(@"\\") || !Directory.Exists(project) || Same(project, root) || new DriveInfo(root).DriveType != DriveType.Fixed)
            throw new InvalidOperationException("Choose an existing local project folder.");
        var guard = new WindowsProjectGuard(project);
        try
        {
            string current = root;
            guard.Hold(current);
            foreach (string part in Path.GetRelativePath(root, project).Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
            { current = Path.Combine(current, part); guard.Hold(current); }
            // Reject 8.3 aliases, trailing-dot normalization and any other
            // lexical route that doesn't match the final handle's long path.
            string canonical = guard.held[^1].Canonical;
            if (!Same(project, canonical)) throw new InvalidOperationException("Project aliases are not accepted.");
            string homeValue = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (string.IsNullOrWhiteSpace(homeValue) || !Path.IsPathFullyQualified(homeValue)) throw new InvalidOperationException("User profile could not be verified.");
            string home = CanonicalProtected(homeValue);
            if (Overlaps(canonical, home) && !canonical.StartsWith(Path.TrimEndingDirectorySeparator(home) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Project overlaps protected account state.");
            string[] protectedPaths = { Path.Combine(home, ".codex"), Path.Combine(home, ".ssh"), Path.Combine(home, ".aws"),
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                Environment.GetEnvironmentVariable("CODEX_HOME") ?? "", Environment.GetEnvironmentVariable("ATTICUS_DIR") ?? "", AppContext.BaseDirectory };
            foreach (string item in protectedPaths)
                if (!string.IsNullOrWhiteSpace(item) && Overlaps(canonical, CanonicalProtected(item))) throw new InvalidOperationException("Project overlaps protected account state.");
            guard.EnsureActive();
            return guard;
        }
        catch { guard.Dispose(); throw; }
    }
    private void Hold(string path)
    {
        var handle = OpenHandle(path);
        try
        {
            var info = Identity(handle); string canonical = FinalPath(handle);
            if (!Same(path, canonical)) throw new InvalidOperationException("Project aliases or reparse paths are not accepted.");
            held.Add(new Held(path, canonical, info.Volume, info.IndexHigh, info.IndexLow, handle));
        }
        catch { handle.Dispose(); throw; }
    }
    internal void EnsureActive()
    {
        if (disposed || held.Count == 0) throw new InvalidOperationException("Project identity is unavailable.");
        foreach (var item in held)
        {
            if (item.Handle.IsClosed || item.Handle.IsInvalid) throw new InvalidOperationException("Project handle is unavailable.");
            var original = Identity(item.Handle);
            using var current = OpenHandle(item.Path);
            var actual = Identity(current);
            if (original.Volume != item.Volume || original.IndexHigh != item.High || original.IndexLow != item.Low || actual.Volume != item.Volume || actual.IndexHigh != item.High || actual.IndexLow != item.Low || !Same(item.Canonical, FinalPath(item.Handle)) || !Same(item.Canonical, FinalPath(current)))
                throw new InvalidOperationException("Project identity changed.");
        }
    }
    public void Dispose() { if (disposed) return; disposed = true; foreach (var h in held) h.Handle.Dispose(); held.Clear(); }
}
