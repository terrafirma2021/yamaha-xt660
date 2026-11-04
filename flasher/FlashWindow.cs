using System;
using System.Drawing;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Xt660 {
    public sealed class MainWindow : Form {
        readonly Library library;readonly ComboBox ports;readonly Button connect,refresh,read,write,cancel;
        readonly Label status,identity;readonly ThinProgress progress;readonly TextBox report;
        BootClient client;CancellationTokenSource cancellation;bool busy,writing;
        string backupDirectory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"XT660","Backups");
        public MainWindow(Library lib) {
            library=lib;ShowIcon=false;Text="XT660 · ECU Flash Tool";ClientSize=new Size(820,620);MinimumSize=new Size(780,610);
            StartPosition=FormStartPosition.CenterScreen;AutoScaleMode=AutoScaleMode.Dpi;
            Font=Theme.Body(11);BackColor=Theme.Background;ForeColor=Theme.Ink;
            var grid=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(30,18,30,18),ColumnCount=1,RowCount=8,BackColor=Theme.Background};
            foreach(int height in new[]{116,76,36,112,38,8})grid.RowStyles.Add(new RowStyle(SizeType.Absolute,height));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent,100));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,43));
            grid.Controls.Add(new BrandHeader{Dock=DockStyle.Fill});
            var connection=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=4,RowCount=2,Margin=new Padding(0)};
            connection.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            foreach(int width in new[]{102,122,112})connection.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,width));
            connection.RowStyles.Add(new RowStyle(SizeType.Absolute,24));connection.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            connection.Controls.Add(Theme.Label("SERIAL CONNECTION",9,Theme.Muted),0,0);
            ports=new ModernCombo{Dock=DockStyle.Fill,Margin=new Padding(0,0,12,0),AccessibleName="COM port"};
            refresh=Button("Refresh",90);connect=Button("Connect",112);((ModernButton)connect).Primary=true;
            var pins=Button("Pinouts",104);
            connection.Controls.Add(ports,0,1);connection.Controls.Add(refresh,1,1);connection.Controls.Add(connect,2,1);connection.Controls.Add(pins,3,1);grid.Controls.Add(connection);
            identity=Theme.Label("NOT CONNECTED",10,Theme.Muted);identity.Dock=DockStyle.Fill;identity.Padding=new Padding(0,3,0,0);grid.Controls.Add(identity);
            var actions=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,Margin=new Padding(0)};
            actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            read=new ModernButton{Text="READ ECU",Subtitle="Save a verified backup",ActionCard=true,Dock=DockStyle.Fill,Margin=new Padding(0,0,8,8)};
            write=new ModernButton{Text="WRITE ECU",Subtitle="Load BIN · automatic checksum",ActionCard=true,Dock=DockStyle.Fill,Margin=new Padding(8,0,0,8)};
            actions.Controls.Add(read);actions.Controls.Add(write);grid.Controls.Add(actions);
            status=Theme.Label("Connect a USB KKL cable to begin.",12,Theme.Ink);status.Dock=DockStyle.Fill;status.AutoEllipsis=true;status.Padding=new Padding(0,5,0,0);grid.Controls.Add(status);
            progress=new ThinProgress{Dock=DockStyle.Fill,Margin=new Padding(0,0,0,4)};grid.Controls.Add(progress);
            report=new TextBox{Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,BorderStyle=BorderStyle.None,ScrollBars=ScrollBars.Vertical,BackColor=Theme.Background,ForeColor=Theme.Muted,Font=Theme.Body(11),Margin=new Padding(0,16,0,0),Text="Read saves a checked backup. Write validates your BIN and corrects its checksum."};grid.Controls.Add(report);
            var footer=new FlowLayoutPanel{Dock=DockStyle.Fill,FlowDirection=FlowDirection.RightToLeft,Margin=new Padding(0)};
            cancel=Button("Cancel",84);cancel.Visible=false;footer.Controls.Add(cancel);
            var note=Theme.Label("9600 baud  /  AUTO CHECKSUM  /  BENCH VALIDATION PENDING",9,Theme.Muted);note.Margin=new Padding(0,14,12,0);footer.Controls.Add(note);grid.Controls.Add(footer);
            Controls.Add(grid);Shown+=(s,e)=>Theme.Chrome(this);
            refresh.Click+=(s,e)=>RefreshPorts();pins.Click+=(s,e)=>{using(var window=new PinoutWindow())window.ShowDialog(this);};
            connect.Click+=async(s,e)=>await Connect();read.Click+=async(s,e)=>await ReadEcu();write.Click+=async(s,e)=>await WriteEcu();cancel.Click+=(s,e)=>{if(cancellation!=null)cancellation.Cancel();};
            FormClosing+=(s,e)=>{if(busy){e.Cancel=true;if(!writing&&cancellation!=null)cancellation.Cancel();else Prompt.Show(this,"Wait for writing and verification to finish. Keep ECU power connected.","Write in progress",MessageBoxButtons.OK,MessageBoxIcon.Information);}else Disconnect();};
            RefreshPorts();SetBusy(false,false);
        }
        static Button Button(string text,int width){return new ModernButton{Text=text,Width=width,Height=38,Margin=new Padding(0,0,8,0)};}
        void RefreshPorts(){string old=ports.SelectedItem as string;ports.Items.Clear();ports.Items.AddRange(SerialPort.GetPortNames().OrderBy(p=>p).Cast<object>().ToArray());if(ports.Items.Count>0)ports.SelectedIndex=Math.Max(0,ports.Items.IndexOf(old??""));connect.Enabled=ports.Items.Count>0;}
        void SetBusy(bool value,bool writeOperation){busy=value;writing=value&&writeOperation;ports.Enabled=refresh.Enabled=!value&&client==null;connect.Enabled=!value&&(client!=null||ports.Items.Count>0);read.Enabled=write.Enabled=!value&&client!=null&&client.Connected;cancel.Visible=value&&!writeOperation;}
        void Progress(FlashProgress update){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(new Action<FlashProgress>(Progress),update);return;}status.Text=update.Message;progress.Value=Math.Max(0,Math.Min(100,update.Percent));}
        void Disconnect(){if(client!=null){client.Dispose();client=null;}connect.Text="Connect";identity.Text="Not connected";}
        void Error(Exception ex,FlashService service=null){
            Disconnect();status.Text=ex is OperationCanceledException?"Cancelled":"Stopped — operation not completed";
            report.Text=ex.Message;
            if(service!=null&&service.BackupPath!=null)report.Text+="\r\n\r\nBackup saved: "+service.BackupPath;
            if(service!=null&&service.ProgrammingStarted)report.Text+="\r\n\r\nWriting started but completion was not verified. Keep power connected; do not start the engine. Use the saved backup for recovery.";
            if(!(ex is OperationCanceledException))Prompt.Show(this,report.Text,"XT660",MessageBoxButtons.OK,MessageBoxIcon.Error);
        }
        async Task Connect(){
            if(client!=null){Disconnect();SetBusy(false,false);status.Text="Disconnected. Cycle ECU power before normal use.";return;}
            if(ports.SelectedItem==null)return;
            if(Prompt.Show(this,"Connect the bench wiring shown in Pinouts. Engine off.\r\n\r\nSwitch ECU power OFF, then click OK.","Connect ECU",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
            SetBusy(true,false);cancellation=new CancellationTokenSource();
            try {
                client=new BootClient(new ComPort((string)ports.SelectedItem));
                if(Prompt.Show(this,"Switch ECU power ON, then click OK immediately.","ECU power",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK){Disconnect();return;}
                Progress(new FlashProgress("Establishing boot session…",0));
                byte[] boot=library.KnownBoot();
                bool known=await Task.Run(()=>{
                    client.Connect(boot,cancellation.Token);
                    var actual=client.Read(0xF800,3,cancellation.Token);
                    return actual.SequenceEqual(boot);
                });
                identity.Text=known?"XT660 boot connected · "+ports.SelectedItem:"Boot connected · unrecognised boot version";
                connect.Text="Disconnect";status.Text="Connected — ready to read";progress.Value=0;
                report.Text=known?"Read ECU saves two matching reads.\r\nWrite ECU loads a BIN, checks its layout and corrects the checksum.\r\n\r\nA verified backup is saved automatically before writing.":"Reading is available. Writing will be blocked because this boot version is not in the reviewed dataset.";
            }catch(Exception ex){Error(ex);}finally{SetBusy(false,false);cancellation.Dispose();cancellation=null;}
        }
        async Task ReadEcu(){
            using(var dialog=new SaveFileDialog{Filter="BIN files (*.bin)|*.bin",FileName="XT660-backup-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".bin",OverwritePrompt=true}) {
                if(dialog.ShowDialog(this)!=DialogResult.OK)return;
                if(library.References.Any(r=>string.Equals(Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,r.Definition.bin_file)),Path.GetFullPath(dialog.FileName),StringComparison.OrdinalIgnoreCase))){Prompt.Show(this,"Choose a new backup filename outside the bundled BINs.","Save backup");return;}
                SetBusy(true,false);cancellation=new CancellationTokenSource();
                try {
                    var service=new FlashService(library,client,Progress);
                    var bytes=await Task.Run(()=>service.ReadVerified(cancellation.Token));
                    SaveBackup(bytes,dialog.FileName);
                    string sum="0x"+Library.Sum(bytes).ToString("X4");
                    status.Text="Backup saved — both reads match";progress.Value=100;
                    report.Text=dialog.FileName+"\r\n\r\n59,392 bytes · CPU 1800–FFFF\r\nChecksum: "+sum+(Library.Sum(bytes)==0xAA55?" — valid":" — does not pass; original bytes preserved")+"\r\nSHA-256: "+Library.Hash(bytes)+"\r\n\r\nKeep this backup before making any changes.";
                }catch(Exception ex){Error(ex);}finally{SetBusy(false,false);cancellation.Dispose();cancellation=null;}
            }
        }
        static void SaveBackup(byte[] bytes,string path){
            string temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try {
                using(var stream=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){stream.Write(bytes,0,bytes.Length);stream.Flush(true);}
                if(!File.ReadAllBytes(temp).SequenceEqual(bytes))throw new IOException("Saved backup verification failed.");
                if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);
            }finally{if(File.Exists(temp))File.Delete(temp);}
        }
        async Task WriteEcu(){
            byte[] input;string path;
            using(var dialog=new OpenFileDialog{Filter="BIN files (*.bin)|*.bin|All files (*.*)|*.*",InitialDirectory=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"bins"),Title="Choose BIN to write"}) {
                if(dialog.ShowDialog(this)!=DialogResult.OK)return;path=dialog.FileName;
                try{input=File.ReadAllBytes(path);library.PrepareWrite(input);}catch(Exception ex){Prompt.Show(this,ex.Message,"BIN check failed",MessageBoxButtons.OK,MessageBoxIcon.Error);return;}
            }
            string checksum=Library.Sum(input)==0xAA55?"Checksum valid — 0xAA55":"Checksum will be corrected automatically to 0xAA55";
            string text=Path.GetFileName(path)+"\r\n"+library.IdentifyApplication(input).Definition.label+" · "+checksum+"\r\n\r\nAlways keep a backup. The tool will save and verify one before writing.\r\nThe connected ECU must match this BIN. Its boot block is preserved.\r\n\r\nKeep power and USB connected until readback verification completes.\r\n\r\nWrite this BIN?";
            if(Prompt.Show(this,text,"Confirm write",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)!=DialogResult.OK)return;
            SetBusy(true,true);var service=new FlashService(library,client,Progress);
            try {
                await Task.Run(()=>service.Write(input,backupDirectory));
                status.Text="Write complete — readback and checksum verified";progress.Value=100;
                report.Text="Backup: "+service.BackupPath+"\r\n\r\nApplication readback matches the prepared BIN byte-for-byte.\r\nStartup checksum: 0xAA55. ECU boot unchanged.\r\n\r\nDisconnect and cycle ECU power before normal use.";
            }catch(Exception ex){Error(ex,service);}finally{SetBusy(false,false);}
        }
        public static string Compare(byte[] a,byte[] b){if(a.Length!=b.Length)return "Files have different lengths; not equal.";int count=a.Select((v,i)=>v!=b[i]?1:0).Sum();return count==0?"Files match byte-for-byte.":count+" bytes differ.";}
    }
}
