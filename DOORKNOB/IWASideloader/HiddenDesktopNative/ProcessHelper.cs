using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Management.Automation;
using System.ComponentModel;

namespace ProcessHelper
{
    [Cmdlet(VerbsLifecycle.Start, "ProcessOnDesktop")]
    public class StartProcessOnDesktopCommand : PSCmdlet
    {
        [Parameter(Mandatory = true, Position = 0)]
        public string ProcessPath { get; set; }

        [Parameter(Position = 1)]
        public string ProcessArgs { get; set; } = "";

        [Parameter(Position = 2)]
        public string DesktopName { get; set; } = "Desktop_" + Guid.NewGuid().ToString("N");

        protected override void ProcessRecord()
        {
            try
            {
                WriteVerbose($"Attempting to create process '{ProcessPath}' on desktop '{DesktopName}'");

                Process process = ProcessHelper.CreateProcessOnDesktop(ProcessPath, ProcessArgs, DesktopName);
                
                if (process != null)
                {
                    WriteObject(process);
                }
                else
                {
                    int errorCode = Marshal.GetLastWin32Error();
                    string errorMessage = new Win32Exception(errorCode).Message;
                    
                    WriteError(new ErrorRecord(
                        new Exception($"Failed to create process on desktop. Error: {errorMessage} (Code: {errorCode})"),
                        "ProcessCreationFailed",
                        ErrorCategory.OperationStopped,
                        null));
                }
            }
            catch (Exception ex)
            {
                WriteError(new ErrorRecord(
                    ex,
                    "UnexpectedError",
                    ErrorCategory.NotSpecified,
                    null));
            }
        }
    }

    public static class ProcessHelper
    {
        // Windows API imports
        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr CreateDesktopEx(
            string lpszDesktop,
            IntPtr lpszDevice,
            IntPtr pDevmode,
            int dwFlags,
            uint dwDesiredAccess,
            IntPtr lpsa,
            ulong heapSize,
            IntPtr pvoid);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr OpenDesktopA(
            string lpszDesktop,
            uint dwFlags,
            bool fInherit,
            uint dwDesiredAccess);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool SetThreadDesktop(IntPtr hDesktop);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool CloseDesktop(IntPtr hDesktop);

        [DllImport("kernel32.dll")]
        private static extern uint GetCurrentThreadId();

        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr GetThreadDesktop(uint dwThreadId);

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        private static extern bool CreateProcess(
            string lpApplicationName,
            string lpCommandLine,
            IntPtr lpProcessAttributes,
            IntPtr lpThreadAttributes,
            bool bInheritHandles,
            uint dwCreationFlags,
            IntPtr lpEnvironment,
            string lpCurrentDirectory,
            ref STARTUPINFO lpStartupInfo,
            ref PROCESS_INFORMATION lpProcessInformation);

        [DllImport("kernel32.dll")]
        private static extern uint GetLastError();

        // Structures for CreateProcess
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
        private struct STARTUPINFO
        {
            public int cb;
            public string lpReserved;
            public string lpDesktop;
            public string lpTitle;
            public uint dwX;
            public uint dwY;
            public uint dwXSize;
            public uint dwYSize;
            public uint dwXCountChars;
            public uint dwYCountChars;
            public uint dwFillAttribute;
            public uint dwFlags;
            public ushort wShowWindow;
            public ushort cbReserved2;
            public IntPtr lpReserved2;
            public IntPtr hStdInput;
            public IntPtr hStdOutput;
            public IntPtr hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct PROCESS_INFORMATION
        {
            public IntPtr hProcess;
            public IntPtr hThread;
            public uint dwProcessId;
            public uint dwThreadId;
        }

        // Constants
        private const uint DESKTOP_CREATEWINDOW = 0x0002;
        private const uint DESKTOP_ENUMERATE = 0x0040;
        private const uint DESKTOP_WRITEOBJECTS = 0x0080;
        private const uint DESKTOP_SWITCHDESKTOP = 0x0100;
        private const uint DESKTOP_CREATEMENU = 0x0004;
        private const uint DESKTOP_HOOKCONTROL = 0x0008;
        private const uint DESKTOP_READOBJECTS = 0x0001;
        private const uint DESKTOP_JOURNALRECORD = 0x0010;
        private const uint DESKTOP_JOURNALPLAYBACK = 0x0020;
        private const uint GENERIC_ALL = 0x10000000;
        private const uint CREATE_NEW_CONSOLE = 0x00000010;
        private const uint NORMAL_PRIORITY_CLASS = 0x00000020;
        private const uint STARTF_USESHOWWINDOW = 0x00000001;
        private const ushort SW_HIDE = 0;

        public static Process CreateProcessOnDesktop(string processPath, string processArgs, string desktopName)
        {
            // Define desktop access rights
            uint ACCESS = DESKTOP_CREATEWINDOW | DESKTOP_ENUMERATE | DESKTOP_WRITEOBJECTS |
                          DESKTOP_SWITCHDESKTOP | DESKTOP_CREATEMENU | DESKTOP_HOOKCONTROL |
                          DESKTOP_READOBJECTS | DESKTOP_JOURNALRECORD | DESKTOP_JOURNALPLAYBACK |
                          GENERIC_ALL;

            // Create or open the desktop
            IntPtr desktopHandle = CreateDesktopEx(
                desktopName,
                IntPtr.Zero,
                IntPtr.Zero,
                0,
                ACCESS,
                IntPtr.Zero,
                0,
                IntPtr.Zero
            );
            
            if (desktopHandle == IntPtr.Zero)
            {
                // Try to open existing desktop
                desktopHandle = OpenDesktopA(desktopName, 0, true, ACCESS);
                if (desktopHandle == IntPtr.Zero)
                {
                    // Failed to create or open desktop
                    return null;
                }
            }
            
            // Prepare to create process
            STARTUPINFO si = new STARTUPINFO();
            si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
            si.lpDesktop = desktopName;
            si.dwFlags = STARTF_USESHOWWINDOW;
            si.wShowWindow = SW_HIDE;
            
            PROCESS_INFORMATION pi = new PROCESS_INFORMATION();
            
            // Create the process - use the command line parameter correctly
            string commandLine = string.IsNullOrEmpty(processArgs) ? processPath : $"\"{processPath}\" {processArgs}";
            
            bool success = CreateProcess(
                null,  // Use command line instead of application name
                commandLine,
                IntPtr.Zero,
                IntPtr.Zero,
                false,
                CREATE_NEW_CONSOLE | NORMAL_PRIORITY_CLASS,
                IntPtr.Zero,
                null,
                ref si,
                ref pi
            );
            
            if (!success)
            {
                // Failed to create process
                CloseDesktop(desktopHandle);
                return null;
            }
            
            // Create a Process object from the process ID
            Process process = null;
            try
            {
                process = Process.GetProcessById((int)pi.dwProcessId);
            }
            catch
            {
                // Failed to get process
                CloseDesktop(desktopHandle);
                return null;
            }            
            return process;
        }
    }
}