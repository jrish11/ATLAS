// Development-only process-tree containment; used before a suspended child resumes.
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Atlas.NativeApprovalDev;

internal sealed class WindowsProcessJob : IDisposable
{
    [StructLayout(LayoutKind.Sequential)] private struct BasicLimits
    {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] private struct IoCounters
    { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)] private struct ExtendedLimits
    {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateJobObjectW(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(SafeFileHandle job, int infoClass, ref ExtendedLimits limits, uint size);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(SafeFileHandle job, IntPtr process);
    private readonly SafeFileHandle job;
    internal WindowsProcessJob(IntPtr processHandle)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException();
        job = CreateJobObjectW(IntPtr.Zero, null);
        if (job.IsInvalid) { int error = Marshal.GetLastWin32Error(); job.Dispose(); throw new Win32Exception(error); }
        try
        {
            var limits = new ExtendedLimits(); limits.Basic.Flags = 0x00002000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimits>()) || !AssignProcessToJobObject(job, processHandle))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Cannot contain provider process.");
        }
        catch { job.Dispose(); throw; }
    }
    public void Dispose() => job.Dispose();
}
