// Test executable only; not included in the release. No physical COM ports.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

namespace Xt660.Tests {
    public sealed class FakeEcu : IBytePort {
        public byte[] Memory;public bool Echo;public int Fragment=17,Programs,Requests,Reads;
        public bool Session,Service,Armed,Disposed;public string Fault;public int CorruptReadAfter=-1;
        readonly Queue<byte> received=new Queue<byte>();
        public FakeEcu(byte[] memory,bool echo){Memory=(byte[])memory.Clone();Echo=echo;}
        public int Available{get{return received.Count;}}
        static byte[] Reply(byte cmd,byte status,byte[] data){
            int length=data.Length+5;var reply=new byte[length];reply[0]=cmd;reply[1]=status;reply[2]=(byte)(length/256);reply[3]=(byte)length;
            Array.Copy(data,0,reply,4,data.Length);int sum=0;for(int n=0;n<length-1;n++)sum+=reply[n];reply[length-1]=(byte)((256-sum%256)%256);return reply;
        }
        public void Write(byte[] frame){
            Requests++;
            if(received.Count!=0)throw new Exception("Outstanding request overwritten");
            if(frame.Length!=frame[2]*256+frame[3]||frame.Sum(b=>(int)b)%256!=0)throw new Exception("Bad host frame");
            byte command=frame[0],status=0;byte[] payload=new byte[0];
            switch(command){
                case 1:
                    if(frame.Length!=21||!frame.Skip(4).Take(16).SequenceEqual(Memory.Skip(0xFF10-0x1800).Take(16)))status=1;else Session=true;
                    break;
                case 2:if(!Session||frame[1]!=1)status=1;else Service=true;break;
                case 3:
                    if(!Service)throw new Exception("Read outside service mode");
                    int address=frame[4]*256+frame[5],length=new[]{2,16,512,2048,256,1024}[frame[1]];
                    if(address<0x1800||address+length>0x10000)throw new Exception("Read outside image");
                    payload=Memory.Skip(address-0x1800).Take(length).ToArray();Reads++;
                    if(CorruptReadAfter>=0&&Reads>CorruptReadAfter)payload[0]^=1;
                    break;
                case 5:
                    if(!Service||!frame.SequenceEqual(new byte[]{5,1,0,9,8,0x20,0x5A,0xA5,0xCA}))throw new Exception("Invalid programming gate");
                    Armed=true;break;
                case 9:
                    int start=frame[1]*256-0x1800;
                    if(!Armed||frame.Length!=2053||start<0||start+2048>0xE000||start%2048!=0)throw new Exception("Unsafe program request");
                    Programs++;
                    if(Fault=="write-status")status=0x20;
                    else {for(int n=0;n<2048;n++)Memory[start+n]=255;Array.Copy(frame,4,Memory,start,2048);if(Fault=="write-readback")Memory[start]^=1;}
                    break;
                default:throw new Exception("Unexpected command "+command);
            }
            if(Fault=="status"&&command==3)status=0x40;
            var reply=Reply(command,status,payload);
            if(Fault=="checksum"&&command==3)reply[reply.Length-1]^=1;
            if(Fault=="command"&&command==3)reply=Reply(4,0,payload);
            if(Fault=="length"&&command==3)reply=Reply(command,0,new byte[16]);
            if(Echo){var sent=(byte[])frame.Clone();if(Fault=="echo"&&command==3)sent[4]^=1;foreach(byte b in sent)received.Enqueue(b);}
            foreach(byte b in reply)received.Enqueue(b);
            if(Fault=="extra"&&command==3)received.Enqueue(0xFF);
            if(Fault=="truncated"&&command==3){var shortReply=received.Take(received.Count-3).ToArray();received.Clear();foreach(byte b in shortReply)received.Enqueue(b);}
        }
        public int Read(byte[] bytes,int offset,int count,int timeout){
            if(received.Count==0)throw new TimeoutException("Test: truncated/disconnected stream");
            int length=Math.Min(Math.Min(Fragment,count),received.Count);for(int n=0;n<length;n++)bytes[offset+n]=received.Dequeue();return length;
        }
        public void Dispose(){Disposed=true;}
    }
    public static class Program {
        static int assertions;
        static void Check(bool condition,string message){assertions++;if(!condition)throw new Exception(message);}
        static void Fails(Action operation,string message){bool failed=false;try{operation();}catch{failed=true;}Check(failed,message);}
        static byte[] Capture(Reference r,byte[] boot){var bytes=new byte[0xE800];Array.Copy(r.Bytes,0x1800-r.Definition.base_address,bytes,0,0xE000);Array.Copy(boot,0,bytes,0xE000,2048);return bytes;}
        public static int Main(string[] args){
            try {
                var lib=new Library(args[0]);var boot=lib.KnownBoot();var baseline=Capture(lib.References.First(r=>r.Definition.id=="xt660-2004-2006-companion"),boot);
                string temp=Path.Combine(Path.GetTempPath(),"xt660-protocol-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(temp);
                try {
                    Check(BootClient.Frame(3,2,new byte[]{0x18,0}).SequenceEqual(new byte[]{3,2,0,7,0x18,0,0xDC}),"First read bytes");
                    foreach(bool echo in new[]{false,true})foreach(int chunk in new[]{1,7,17,517,4096}){
                        var ecu=new FakeEcu(baseline,echo){Fragment=chunk};using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);Check(client.CableEcho==echo,"Echo detection");
                            Check(client.ReadImage(null,CancellationToken.None).SequenceEqual(baseline),"Full read, every byte");
                            Check(ecu.Reads==116&&ecu.Programs==0,"Read coverage / no writes");
                        }
                    }
                    foreach(string fault in new[]{"checksum","command","length","status","extra","truncated","echo"}){
                        var ecu=new FakeEcu(baseline,true);using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);ecu.Fault=fault;
                            Fails(()=>client.Read(0x1800,2,CancellationToken.None),"Reject "+fault);Check(!client.Connected,"Close failed session");
                            int requests=ecu.Requests;Fails(()=>client.Read(0x1800,2,CancellationToken.None),"No subsequent request");Check(ecu.Requests==requests,"No retry after "+fault);
                        }
                    }
                    foreach(var reference in lib.References){
                        var live=Capture(reference,boot);var input=(byte[])reference.Bytes.Clone();
                        int map=Array.FindIndex(reference.Maps,b=>b);input[map]^=1;
                        var ecu=new FakeEcu(live,true);using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);
                            Fails(()=>client.ProgramBlock(0x1800,new byte[2048]),"Unarmed program rejected");
                            var service=new FlashService(lib,client,null);service.Write(input,temp);
                            Check(File.ReadAllBytes(service.BackupPath).SequenceEqual(live),"Immutable automatic backup "+reference.Definition.id);
                            var expected=lib.PrepareWrite(input);
                            Check(ecu.Memory.Take(0xE000).SequenceEqual(expected.Skip(0x1800-Library.Base(expected)).Take(0xE000)),"Application programmed "+reference.Definition.id);
                            Check(ecu.Memory.Skip(0xE000).SequenceEqual(boot)&&Library.Sum(ecu.Memory)==0xAA55,"Boot preserved / checksum "+reference.Definition.id);
                            Check(input[map]==(byte)(reference.Bytes[map]^1),"Input preserved");
                            Check(ecu.Programs>=1&&ecu.Programs<=2,"Only changed blocks written");
                            int previous=ecu.Programs;service.Write(expected,temp);Check(ecu.Programs==previous,"Already matching file has no erase");
                        }
                    }
                    foreach(string fault in new[]{"write-status","write-readback"}){
                        var input=(byte[])baseline.Clone();input[0x1B66-0x1800]^=1;
                        var ecu=new FakeEcu(baseline,true){Fault=fault};using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);var service=new FlashService(lib,client,null);
                            Fails(()=>service.Write(input,temp),"Fail on "+fault);Check(ecu.Programs==1,"No destructive retry");Check(File.Exists(service.BackupPath),"Backup before first write");
                        }
                    }
                    var badBoot=(byte[])baseline.Clone();badBoot[0xE100]^=1;
                    foreach(var memory in new[]{baseline,badBoot}){
                        var ecu=new FakeEcu(memory,true);using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);var service=new FlashService(lib,client,null);
                            var wrong=lib.References.First(r=>r.Definition.code_family=="late").Bytes;
                            Fails(()=>service.Write(memory==baseline?wrong:baseline,temp),"Reject wrong family / boot");Check(ecu.Programs==0&&!ecu.Armed,"Reject before program gate");
                        }
                    }
                    {
                        var ecu=new FakeEcu(baseline,false){CorruptReadAfter=116};using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);var service=new FlashService(lib,client,null);
                            Fails(()=>service.Write(baseline,temp),"Mismatched backup passes");Check(ecu.Programs==0&&service.BackupPath==null,"No write without matching backup");
                        }
                    }
                    {
                        var ecu=new FakeEcu(baseline,false);using(var client=new BootClient(ecu,delegate{})){
                            client.Connect(boot,CancellationToken.None);var service=new FlashService(lib,client,null);
                            string blocked=Path.Combine(temp,"not-a-directory");File.WriteAllText(blocked,"test");
                            Fails(()=>service.Write(baseline,blocked),"Backup disk failure");Check(ecu.Programs==0&&!ecu.Armed,"No write without saved backup");
                            client.PrepareProgramming(CancellationToken.None);
                            foreach(int address in new[]{0,0x17FF,0x1801,0xF800,0xFFFF})Fails(()=>client.ProgramBlock(address,new byte[2048]),"Reject program address "+address);
                            var stop=new CancellationToken(true);int requests=ecu.Requests;
                            Fails(()=>client.ReadImage(null,stop),"Cancellation");Check(ecu.Requests==requests,"Cancelled read sends nothing");
                        }
                    }
                } finally {Directory.Delete(temp,true);}
                Console.WriteLine("PASS: "+assertions+" protocol checks; 9 BIN layouts, echo/no-echo, fragmented reads, automatic backups, checksum correction, bounded writes, readback and failure stops. No COM port opened.");return 0;
            }catch(Exception ex){Console.Error.WriteLine(ex);return 1;}
        }
    }
}
