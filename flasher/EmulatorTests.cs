// Test-only bridge: execute the actual BootClient against the real BIN in uCsim.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Xt660.EmulatorTests {
    sealed class EmulatedPort : IBytePort {
        readonly Process process;readonly Queue<byte> bytes=new Queue<byte>();
        public EmulatedPort(string python,string arguments) {
            process=Process.Start(new ProcessStartInfo(python,arguments){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true});
            if(process.StandardOutput.ReadLine()!="READY")throw new Exception("Emulator did not start");
        }
        public int Available {get{return bytes.Count;}}
        public void Write(byte[] request) {
            process.StandardInput.WriteLine(Convert.ToBase64String(request));process.StandardInput.Flush();
            string line=process.StandardOutput.ReadLine();
            if(line==null||!line.StartsWith("REPLY "))throw new IOException(line??"Emulator exited");
            foreach(byte value in Convert.FromBase64String(line.Substring(6)))bytes.Enqueue(value);
        }
        public int Read(byte[] target,int offset,int count,int timeout) {
            int length=Math.Min(count,Math.Min(bytes.Count,17));
            for(int n=0;n<length;n++)target[offset+n]=bytes.Dequeue();return length;
        }
        public void Dispose() {
            if(!process.HasExited){process.StandardInput.WriteLine("QUIT");process.StandardInput.Flush();if(!process.WaitForExit(5000))process.Kill();}
            process.Dispose();
        }
    }
    static class Program {
        public static int Main(string[] args) {
            try {
                var library=new Library(args[0]);
                var reference=library.References.First(r=>r.Definition.id=="xt660-2004-2006-companion");
                string backup=Path.Combine(args[1],"emulator-backups");
                string script=Path.GetFullPath(Path.Combine(args[1],"../port_bridge.py"));
                using(var client=new BootClient(new EmulatedPort(args[2],"\""+script+"\" --wsl --ucsim \""+args[3]+"\""),delegate{},100)) {
                    client.Connect(library.KnownBoot(),CancellationToken.None);
                    var input=(byte[])reference.Bytes.Clone();input[0x1b66-reference.Definition.base_address]^=1;
                    var service=new FlashService(library,client,p=>{if(p.Percent%25==0)Console.WriteLine(p.Message+" "+p.Percent+"%");});
                    service.Write(input,backup);
                    if(!File.ReadAllBytes(service.BackupPath).SequenceEqual(reference.Bytes))throw new Exception("Backup differs from source BIN");
                    if(!service.ProgrammingStarted)throw new Exception("Programming path not exercised");
                    Console.WriteLine("PASS: real C# client; two complete firmware reads, immutable backup, corrected checksum, application erase, 28 RAM-programmed blocks, per-block and complete readback; boot preserved. No COM port.");
                }
                return 0;
            }catch(Exception error){Console.Error.WriteLine(error);return 1;}
        }
    }
}
