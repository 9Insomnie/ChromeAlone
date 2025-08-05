using System;
using System.IO;

namespace Chrome
{
    internal class Program
    {
        /**
        var port = chrome.runtime.connectNative('com.chrome.alone');
        port.onMessage.addListener(function(msg) {
          console.log("Received: " + msg["data"]);
        });
        port.onDisconnect.addListener(function() {
          console.log("Disconnected");
        });
        port.postMessage({"message":"cmd.exe|/c dir"});
         */
        
        public static void Main(string[] args)
        {
            string message = NativeMessaging.OpenStandardStreamIn();
            if (!string.IsNullOrEmpty(message))
            {
                // File.WriteAllText("./message.txt", message);
                if (message.Contains("|"))
                {
                    string output = NativeMessaging.ParseMessage(message);
                    NativeMessaging.OpenStandardStreamOut(output);
                }
            }
        }

        // public static void Test()
        // {
        //     string output = NativeMessaging.ParseMessage("{\"message\":\"cmd.exe|/c dir\"}");
        //     NativeMessaging.OpenStandardStreamOut(output);
        // }
    }
}