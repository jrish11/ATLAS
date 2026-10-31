// Windows-only, development process launcher. The initial thread is suspended
// until assigned to a kill-on-close job. Only three explicitly listed stdio
// handles are inheritable. Not a substitute for a provider sandbox.
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Atlas.NativeApprovalDev;

internal sealed class ContainedProviderProcess : IDisposable
{
    [StructLayout(LayoutKind.Sequential)] private struct SecurityAttributes { public int Length; public IntPtr Descriptor; public int Inherit; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct StartupInfo
    {
        public int Size; public string Reserved, Desktop, Title;
        public uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
        public ushort Show, Reserved2Size; public IntPtr Reserved2, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)] private struct StartupInfoEx { public StartupInfo Startup; public IntPtr Attributes; }
    [StructLayout(LayoutKind.Sequential)] private struct ProcessInformation { public IntPtr Process, Thread; public uint ProcessId, ThreadId; }
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool CreatePipe(out SafeFileHandle read, out SafeFileHandle write, ref SecurityAttributes attributes, uint size);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool SetHandleInformation(SafeFileHandle handle, uint mask, uint flags);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)] private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, ref SecurityAttributes attributes, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, int flags, ref IntPtr size);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr attribute, IntPtr value, IntPtr size, IntPtr previous, IntPtr returned);
    [DllImport("kernel32.dll")] private static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)] private static extern bool CreateProcessW(string app, StringBuilder command, IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string directory, ref StartupInfoEx startup, out ProcessInformation information);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern uint ResumeThread(SafeFileHandle thread);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool TerminateProcess(SafeFileHandle process, uint code);

    internal Process Process { get; }
    internal Stream Input { get; }
    internal Stream Output { get; }
    private readonly WindowsProcessJob job;
    private bool disposed;
    private ContainedProviderProcess(Process process, Stream input, Stream output, WindowsProcessJob job)
    { Process = process; Input = input; Output = output; this.job = job; }

    // Implements the Windows CRT command-line quoting convention.
    private static string Quote(string arg)
    {
        var text = new StringBuilder("\""); int slashes = 0;
        foreach (char c in arg)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { text.Append('\\', slashes * 2 + 1); text.Append('"'); slashes = 0; continue; }
            text.Append('\\', slashes); slashes = 0; text.Append(c);
        }
        text.Append('\\', slashes * 2); return text.Append('"').ToString();
    }
    private static void Check(bool ok, string operation) { if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error(), operation); }
    internal static ContainedProviderProcess Start(ProcessStartInfo info, bool failBeforeResumeForTest = false, bool mergeErrorWithOutput = false)
    {
        if (!OperatingSystem.IsWindows() || info.UseShellExecute || !info.RedirectStandardInput || !info.RedirectStandardOutput || !Path.IsPathFullyQualified(info.FileName) || !string.IsNullOrEmpty(info.Arguments)) throw new InvalidOperationException("Explicit provider launch arguments are required.");
        SafeFileHandle childIn = null, parentIn = null, parentOut = null, childOut = null, childError = null, processHandle = null, threadHandle = null;
        WindowsProcessJob job = null; Process process = null; Stream input = null, output = null;
        IntPtr attr = IntPtr.Zero, handles = IntPtr.Zero, environment = IntPtr.Zero; bool attrInitialized = false;
        try
        {
            var security = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), Inherit = 1 };
            Check(CreatePipe(out childIn, out parentIn, ref security, 0), "Create stdin pipe");
            Check(CreatePipe(out parentOut, out childOut, ref security, 0), "Create stdout pipe");
            Check(SetHandleInformation(parentIn, 1, 0) && SetHandleInformation(parentOut, 1, 0), "Protect parent pipe handles");
            if (!mergeErrorWithOutput)
            {
                childError = CreateFileW("NUL", 0x40000000, 3, ref security, 3, 0, IntPtr.Zero);
                if (childError.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "Open stderr sink");
            }
            IntPtr size = IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref size);
            if (size == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "Query attribute list size");
            attr = Marshal.AllocHGlobal(size);
            Check(InitializeProcThreadAttributeList(attr, 1, 0, ref size), "Initialize handle list"); attrInitialized = true;
            handles = Marshal.AllocHGlobal(IntPtr.Size * 3);
            Marshal.WriteIntPtr(handles, 0, childIn.DangerousGetHandle());
            Marshal.WriteIntPtr(handles, IntPtr.Size, childOut.DangerousGetHandle());
            if (!mergeErrorWithOutput) Marshal.WriteIntPtr(handles, IntPtr.Size * 2, childError.DangerousGetHandle());
            int handleCount = mergeErrorWithOutput ? 2 : 3;
            Check(UpdateProcThreadAttribute(attr, 0, new IntPtr(0x00020002), handles, new IntPtr(IntPtr.Size * handleCount), IntPtr.Zero, IntPtr.Zero), "Set explicit handle list");
            var startup = new StartupInfoEx { Attributes = attr, Startup = new StartupInfo { Size = Marshal.SizeOf<StartupInfoEx>(), Flags = 0x100, Input = childIn.DangerousGetHandle(), Output = childOut.DangerousGetHandle(), Error = mergeErrorWithOutput ? childOut.DangerousGetHandle() : childError.DangerousGetHandle() } };
            string command = string.Join(" ", new[] { info.FileName }.Concat(info.ArgumentList).Select(Quote));
            if (command.Length >= 32767) throw new InvalidOperationException("Provider command too long.");
            string block = string.Join("\0", info.Environment.Where(p => p.Value != null).OrderBy(p => p.Key, StringComparer.OrdinalIgnoreCase).Select(p => p.Key + "=" + p.Value)) + "\0\0";
            environment = Marshal.StringToHGlobalUni(block);
            const uint flags = 0x00000004 | 0x00000400 | 0x00080000 | 0x08000000; // suspended, Unicode env, startup-info-ex, no window
            Check(CreateProcessW(info.FileName, new StringBuilder(command), IntPtr.Zero, IntPtr.Zero, true, flags, environment, string.IsNullOrEmpty(info.WorkingDirectory) ? null : info.WorkingDirectory, ref startup, out var raw), "Create suspended provider");
            processHandle = new SafeFileHandle(raw.Process, true); threadHandle = new SafeFileHandle(raw.Thread, true);
            job = new WindowsProcessJob(processHandle.DangerousGetHandle());
            process = Process.GetProcessById(checked((int)raw.ProcessId));
            input = new FileStream(parentIn, FileAccess.Write, 4096, false); parentIn = null;
            output = new FileStream(parentOut, FileAccess.Read, 4096, false); parentOut = null;
            childIn.Dispose(); childIn = null; childOut.Dispose(); childOut = null; childError?.Dispose(); childError = null;
            if (failBeforeResumeForTest) throw new InvalidOperationException("Fixture stopped before resume.");
            if (ResumeThread(threadHandle) == uint.MaxValue) throw new Win32Exception(Marshal.GetLastWin32Error(), "Resume contained provider");
            var result = new ContainedProviderProcess(process, input, output, job);
            process = null; input = null; output = null; job = null;
            return result;
        }
        catch
        {
            if (processHandle != null && !processHandle.IsInvalid) TerminateProcess(processHandle, 1);
            job?.Dispose(); input?.Dispose(); output?.Dispose(); process?.Dispose(); throw;
        }
        finally
        {
            processHandle?.Dispose(); threadHandle?.Dispose(); childIn?.Dispose(); parentIn?.Dispose(); parentOut?.Dispose(); childOut?.Dispose(); childError?.Dispose();
            if (attrInitialized) DeleteProcThreadAttributeList(attr);
            if (attr != IntPtr.Zero) Marshal.FreeHGlobal(attr);
            if (handles != IntPtr.Zero) Marshal.FreeHGlobal(handles);
            if (environment != IntPtr.Zero) Marshal.FreeHGlobal(environment);
        }
    }
    public void Dispose()
    {
        if (disposed) return; disposed = true;
        job.Dispose(); Input.Dispose(); Output.Dispose(); Process.Dispose();
    }
}
