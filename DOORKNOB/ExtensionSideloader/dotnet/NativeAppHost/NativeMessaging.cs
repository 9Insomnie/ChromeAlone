using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;

namespace Chrome
{
    public class NativeMessaging
    {
        public static string ParseMessage(string nativeMessage)
        {
            string command, args;
            try
            {
                string parsedMessage = nativeMessage.Substring("{\"message\":\"".Length, nativeMessage.Length - "{\"message\":\"".Length - "\"}".Length);
                // File.AppendAllText("./message.txt", parsedMessage);
                command = parsedMessage.Split('|')[0];
                args = string.Join("|", parsedMessage.Split('|').Skip(1).ToArray());
                // File.AppendAllText("./message.txt", string.Format("\n{0}\n{1}",command, args));
            }
            catch (Exception)
            {
                // File.AppendAllText("./message.txt", e.Message);
                return $"Message \"{nativeMessage}\" was not correctly formatted";
            }
            
            
            Process process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = command,
                    Arguments = args,
                    UseShellExecute = false, RedirectStandardOutput = true,
                    CreateNoWindow = true
                }
            };

            try
            {
                process.Start();

                string output = "";
            
                while (!process.StandardOutput.EndOfStream)
                {
                    var line = process.StandardOutput.ReadLine();
                    output += line + "\n";
                }
 
                process.WaitForExit();

                return output;
            }
            catch (Exception e)
            {
                return $"An Error happened: {e.Message}";
            }
        }
        
        // Token: 0x0600000A RID: 10 RVA: 0x00002BD8 File Offset: 0x00000DD8
        public static string OpenStandardStreamIn()
        {
            Stream stream = Console.OpenStandardInput();
            byte[] array = new byte[4];
            stream.Read(array, 0, 4);
            int num = BitConverter.ToInt32(array, 0);
            string text = "";
            for (int i = 0; i < num; i++)
            {
                text += (char)stream.ReadByte();
            }
            return text;
        }

        // Token: 0x0600000B RID: 11 RVA: 0x00002C30 File Offset: 0x00000E30
        public static void OpenStandardStreamOut(string stringData)
        {
            string encodedData = Convert.ToBase64String(Encoding.UTF8.GetBytes(stringData));
            string message = string.Format("{{\"data\":\"{0}\"}}",encodedData);
            int length = message.Length;
            Stream stream = Console.OpenStandardOutput();
            stream.WriteByte((byte)(length & 255));
            stream.WriteByte((byte)(length >> 8 & 255));
            stream.WriteByte((byte)(length >> 16 & 255));
            stream.WriteByte((byte)(length >> 24 & 255));
            stream.Write(Encoding.UTF8.GetBytes(message),0,length);
            stream.Flush();
        }
    }
}