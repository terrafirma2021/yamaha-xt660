using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Threading;

namespace Xt660 {
    public interface IBytePort : IDisposable {
        int Available { get; }
        void Write(byte[] bytes);
        int Read(byte[] bytes,int offset,int count,int timeout);
    }
    public sealed class ComPort : IBytePort {
        readonly SerialPort port;
        public ComPort(string name) {
            port=new SerialPort(name,9600,Parity.None,8,StopBits.One) {
                Handshake=Handshake.None,DtrEnable=false,RtsEnable=false,
                ReadTimeout=100,WriteTimeout=5000,ReadBufferSize=16384,WriteBufferSize=4096,
                DiscardNull=false,ParityReplace=0
            };
            try { port.Open();port.DiscardInBuffer(); } catch {port.Dispose();throw;}
        }
        public int Available {get{return port.BytesToRead;}}
        public void Write(byte[] bytes) {port.Write(bytes,0,bytes.Length);}
        public int Read(byte[] bytes,int offset,int count,int timeout) {
            port.ReadTimeout=Math.Max(1,timeout);
            try{return port.Read(bytes,offset,count);}catch(TimeoutException){return 0;}
        }
        public void Dispose(){port.Dispose();}
    }
    public sealed class BootClient : IDisposable {
        readonly IBytePort port;readonly Action<int> delay;readonly object gate=new object();
        bool? echo;bool failed,entered,armed;bool disposed;
        public bool Connected {get{return entered&&!failed&&!disposed;}}
        public bool CableEcho {get{return echo==true;}}
        public BootClient(IBytePort port,Action<int> delay=null){this.port=port;this.delay=delay??Thread.Sleep;}
        public static byte[] Frame(byte command,byte parameter,byte[] payload) {
            if(command>15||payload.Length+5>0x805)throw new ArgumentException("Invalid boot frame.");
            int length=payload.Length+5;var bytes=new byte[length];
            bytes[0]=command;bytes[1]=parameter;bytes[2]=(byte)(length>>8);bytes[3]=(byte)length;
            Buffer.BlockCopy(payload,0,bytes,4,payload.Length);
            bytes[length-1]=unchecked((byte)-bytes.Sum(b=>(int)b));return bytes;
        }
        byte[] Exact(int length,Stopwatch clock,int timeout,CancellationToken cancel) {
            var bytes=new byte[length];int count=0;
            while(count<length) {
                cancel.ThrowIfCancellationRequested();
                int remaining=timeout-(int)clock.ElapsedMilliseconds;
                if(remaining<=0)throw new TimeoutException("ECU reply timed out. No command was retried.");
                int read=port.Read(bytes,count,length-count,Math.Min(remaining,100));
                if(read<0||read>length-count)throw new IOException("Invalid adapter read count.");
                count+=read;
            }
            return bytes;
        }
        byte[] Exchange(byte[] request,int payloadLength,int timeout,CancellationToken cancel) {
            lock(gate) {
                if(failed||disposed)throw new IOException("Connection is no longer usable. Reconnect the ECU.");
                try {
                    cancel.ThrowIfCancellationRequested();
                    delay(40); // Matches host spacing; deadlines are bounded, commands are never replayed.
                    if(port.Available!=0)throw new IOException("Unexpected bytes before a request. Reconnect with the ECU powered off.");
                    var clock=Stopwatch.StartNew();port.Write(request);
                    byte[] header;
                    if(!echo.HasValue) {
                        // Session request and reply have different lengths (21 vs 5).
                        // Decide from the full header and validate every echo byte.
                        header=Exact(4,clock,timeout,cancel);
                        bool detected=header.SequenceEqual(request.Take(4));
                        if(detected) {
                            if(!Exact(request.Length-4,clock,timeout,cancel).SequenceEqual(request.Skip(4)))throw new IOException("Adapter echo differs from the transmitted frame.");
                            header=Exact(4,clock,timeout,cancel);
                        }
                        echo=detected;
                    } else {
                        if(echo.Value&&!Exact(request.Length,clock,timeout,cancel).SequenceEqual(request))throw new IOException("Adapter echo differs from the transmitted frame.");
                        header=Exact(4,clock,timeout,cancel);
                    }
                    int length=(header[2]<<8)|header[3];
                    if(length<5||length>0x805)throw new IOException("Invalid ECU reply length.");
                    var tail=Exact(length-4,clock,timeout,cancel);
                    if(((header.Sum(b=>(int)b)+tail.Sum(b=>(int)b))&255)!=0)throw new IOException("ECU reply checksum failed.");
                    if(header[0]!=request[0]||header[1]!=0)throw new IOException("ECU rejected command "+request[0].ToString("X2")+" (reply "+header[0].ToString("X2")+", status "+header[1].ToString("X2")+").");
                    if(length!=payloadLength+5)throw new IOException("Unexpected ECU payload length.");
                    if(port.Available!=0)throw new IOException("Unexpected extra bytes after ECU reply.");
                    return tail.Take(payloadLength).ToArray();
                } catch {failed=true;entered=false;throw;}
            }
        }
        public void Connect(byte[] knownBoot,CancellationToken cancel) {
            if(entered||echo.HasValue)throw new InvalidOperationException("Start a fresh connection.");
            if(knownBoot.Length!=2048)throw new ArgumentException("Invalid boot profile.");
            Exchange(Frame(1,0,knownBoot.Skip(0x710).Take(16).ToArray()),0,3000,cancel);
            Exchange(Frame(2,1,new byte[0]),0,3000,cancel);
            entered=true;
        }
        public byte[] Read(int address,int mode,CancellationToken cancel) {
            if(!Connected)throw new IOException("Connect to the ECU first.");
            int[] lengths={2,16,512,2048,256,1024};
            if(mode<0||mode>=lengths.Length||address<0||address+lengths[mode]>0x10000)throw new ArgumentOutOfRangeException("address");
            return Exchange(Frame(3,(byte)mode,new byte[]{(byte)(address>>8),(byte)address}),lengths[mode],5000,cancel);
        }
        public byte[] ReadImage(Action<int,int> progress,CancellationToken cancel) {
            var image=new byte[0xE800];
            for(int n=0;n<116;n++) {
                byte[] block=Read(0x1800+n*512,2,cancel);Buffer.BlockCopy(block,0,image,n*512,512);
                if(progress!=null)progress(n+1,116);
            }
            return image;
        }
        public void PrepareProgramming(CancellationToken cancel) {
            if(!Connected)throw new IOException("Connect to the ECU first.");
            // Firmware F9C8 accepts 0820=5AA5 only in service-loop state 0022=5A.
            // This is the same RAM gate sent by the original XT writer.
            Exchange(Frame(5,1,new byte[]{8,0x20,0x5A,0xA5}),0,3000,cancel);
            armed=true;
        }
        public void ProgramBlock(int address,byte[] data) {
            if(!Connected)throw new IOException("Connect to the ECU first.");
            if(!armed)throw new InvalidOperationException("Programming has not been prepared.");
            if(data.Length!=2048||address<0x1800||address+2048>0xF800||address%2048!=0)
                throw new ArgumentException("Only aligned application blocks from 1800 through F7FF may be written.");
            // Once sent, wait for completion. Never cancel/retry an erase or program command.
            Exchange(Frame(9,(byte)(address>>8),data),0,15000,CancellationToken.None);
        }
        public void Dispose(){disposed=true;entered=false;port.Dispose();}
    }
    public sealed class FlashProgress {
        public string Message;public int Percent;
        public FlashProgress(string message,int percent){Message=message;Percent=percent;}
    }
    public sealed class FlashService {
        readonly Library library;readonly BootClient client;readonly Action<FlashProgress> progress;
        public string BackupPath {get;private set;}
        public bool ProgrammingStarted {get;private set;}
        public FlashService(Library library,BootClient client,Action<FlashProgress> progress) {
            this.library=library;this.client=client;this.progress=progress??delegate{};
        }
        public byte[] ReadVerified(CancellationToken cancel) {
            progress(new FlashProgress("Reading backup — pass 1 of 2",0));
            var first=client.ReadImage((n,total)=>progress(new FlashProgress("Reading backup — pass 1 of 2",n*50/total)),cancel);
            var second=client.ReadImage((n,total)=>progress(new FlashProgress("Checking backup — pass 2 of 2",50+n*50/total)),cancel);
            if(!first.SequenceEqual(second))throw new IOException("The two ECU reads differ. No verified backup was saved.");
            return first;
        }
        public void Write(byte[] input,string backupDirectory) {
            BackupPath=null;ProgrammingStarted=false;
            var prepared=library.PrepareWrite(input);
            var baseline=ReadVerified(CancellationToken.None);
            if(!baseline.Skip(0xE000).SequenceEqual(library.KnownBoot()))throw new InvalidDataException("The connected ECU boot is not supported. Nothing was written.");
            var compatible=library.References.Where(r=>library.MatchesApplication(baseline,r)&&library.MatchesApplication(prepared,r)).ToList();
            if(compatible.Count==0)throw new InvalidDataException("The BIN does not match the connected ECU application. Nothing was written.");
            Directory.CreateDirectory(backupDirectory);
            string name="XT660-"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,8)+".bin";
            BackupPath=Path.Combine(backupDirectory,name);
            using(var file=new FileStream(BackupPath,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {file.Write(baseline,0,baseline.Length);file.Flush(true);}
            if(!File.ReadAllBytes(BackupPath).SequenceEqual(baseline))throw new IOException("Backup file verification failed. Nothing was written.");
            var desired=(byte[])baseline.Clone();
            Buffer.BlockCopy(prepared,0x1800-Library.Base(prepared),desired,0,0xE000);
            if(Library.Sum(desired)!=0xAA55)throw new InvalidDataException("Prepared startup checksum failed. Nothing was written.");
            var changed=new List<int>();
            for(int offset=0;offset<0xE000;offset+=2048)
                if(!desired.Skip(offset).Take(2048).SequenceEqual(baseline.Skip(offset).Take(2048)))changed.Add(offset);
            if(changed.Count>0) {
                client.PrepareProgramming(CancellationToken.None);
                for(int n=0;n<changed.Count;n++) {
                    int offset=changed[n];ProgrammingStarted=true;
                    progress(new FlashProgress("Writing "+(offset+0x1800).ToString("X4")+"–"+(offset+0x1FFF).ToString("X4"),n*100/changed.Count));
                    client.ProgramBlock(offset+0x1800,desired.Skip(offset).Take(2048).ToArray());
                    // Acknowledgement alone is insufficient: read the addressed block back.
                    for(int part=0;part<4;part++) {
                        var actual=client.Read(offset+0x1800+part*512,2,CancellationToken.None);
                        if(!actual.SequenceEqual(desired.Skip(offset+part*512).Take(512)))throw new IOException("Readback differs at "+(offset+0x1800+part*512).ToString("X4")+". Writing stopped.");
                    }
                }
            }
            var final=client.ReadImage((n,total)=>progress(new FlashProgress("Verifying complete application and unchanged boot",n*100/total)),CancellationToken.None);
            if(!final.SequenceEqual(desired)||Library.Sum(final)!=0xAA55)throw new IOException("Final readback verification failed.");
            progress(new FlashProgress(changed.Count==0?"ECU already matches — verified":"Write complete — readback and checksum verified",100));
        }
    }
}
