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
        readonly ModernButton flashNav,pinoutsNav,themeToggle;
        readonly Control flashPage,pinoutPage;readonly Panel content;
        readonly Label status,identity;readonly ThinProgress progress;readonly RichTextBox report;
        BootClient client;CancellationTokenSource cancellation;bool busy,writing;
        string backupDirectory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"XT660","Backups");
        public MainWindow(Library lib) {
            Theme.LoadPreference();library=lib;ShowIcon=false;Text="XT660 · ECU Flash Tool";
            AutoScaleDimensions=new SizeF(96,96);AutoScaleMode=AutoScaleMode.Dpi;
            Font=Theme.Body(10.5f);FormBorderStyle=FormBorderStyle.FixedSingle;MaximizeBox=false;
            ClientSize=new Size(1000,720);StartPosition=FormStartPosition.CenterScreen;
            var shell=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(28,18,28,18),ColumnCount=1,RowCount=4};
            shell.RowStyles.Add(new RowStyle(SizeType.Absolute,78));shell.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
            shell.RowStyles.Add(new RowStyle(SizeType.Percent,100));shell.RowStyles.Add(new RowStyle(SizeType.Absolute,30));
            var header=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=new Padding(0)};
            header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,120));
            header.Controls.Add(new BrandHeader{Dock=DockStyle.Fill,Margin=new Padding(0)});
            themeToggle=new ModernButton{Width=116,Height=34,Anchor=AnchorStyles.Right|AnchorStyles.Top,Margin=new Padding(0,15,0,0)};
            header.Controls.Add(themeToggle);shell.Controls.Add(header);
            var navigation=new FlowLayoutPanel{Dock=DockStyle.Fill,Margin=new Padding(0),WrapContents=false};
            flashNav=new ModernButton{Text="Flash",Navigation=true,Width=104,Height=40,Margin=new Padding(0)};
            pinoutsNav=new ModernButton{Text="Pinouts",Navigation=true,Width=104,Height=40,Margin=new Padding(0)};
            navigation.Controls.Add(flashNav);navigation.Controls.Add(pinoutsNav);shell.Controls.Add(navigation);
            content=new Panel{Dock=DockStyle.Fill,Margin=new Padding(0)};shell.Controls.Add(content);
            var grid=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(0,18,0,0),ColumnCount=1,RowCount=7,Margin=new Padding(0),AccessibleName="Flash page"};
            foreach(int height in new[]{65,29,96,34,6,31})grid.RowStyles.Add(new RowStyle(SizeType.Absolute,height));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            var connection=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=3,RowCount=2,Margin=new Padding(0)};
            connection.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            connection.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,104));connection.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,120));
            connection.RowStyles.Add(new RowStyle(SizeType.Absolute,23));connection.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            connection.Controls.Add(Theme.Label("SERIAL CONNECTION",9,Theme.Muted),0,0);
            ports=new ModernCombo{Dock=DockStyle.Fill,Margin=new Padding(0,0,16,0),AccessibleName="COM port"};
            refresh=Button("Refresh",92);connect=Button("Connect",116);((ModernButton)connect).Primary=true;
            connection.Controls.Add(ports,0,1);connection.Controls.Add(refresh,1,1);connection.Controls.Add(connect,2,1);grid.Controls.Add(connection);
            identity=Theme.Label("NOT CONNECTED",9,Theme.Muted);identity.Dock=DockStyle.Fill;grid.Controls.Add(identity);
            var actions=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,Margin=new Padding(0)};
            actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            read=new ModernButton{Text="READ ECU",Subtitle="Save a verified backup",ActionCard=true,Dock=DockStyle.Fill,Margin=new Padding(0,0,8,10)};
            write=new ModernButton{Text="WRITE ECU",Subtitle="Load BIN · automatic checksum",ActionCard=true,Dock=DockStyle.Fill,Margin=new Padding(8,0,0,10)};
            actions.Controls.Add(read);actions.Controls.Add(write);grid.Controls.Add(actions);
            status=Theme.Label("Connect a USB KKL cable to begin.",10.5f,Theme.Ink);status.Dock=DockStyle.Fill;status.AutoEllipsis=true;status.Padding=new Padding(0,4,0,0);grid.Controls.Add(status);
            progress=new ThinProgress{Dock=DockStyle.Fill,Margin=new Padding(0,0,0,3)};grid.Controls.Add(progress);
            var activity=Theme.Label("ACTIVITY",9,Theme.Muted);activity.Padding=new Padding(0,10,0,0);grid.Controls.Add(activity);
            report=new RichTextBox{Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,BorderStyle=BorderStyle.None,ScrollBars=RichTextBoxScrollBars.Vertical,DetectUrls=false,Tag="log",Font=Theme.Body(10.5f),Margin=new Padding(0,4,0,8),Text="Read saves a checked backup. Write validates your BIN and corrects its checksum."};grid.Controls.Add(report);
            flashPage=grid;pinoutPage=new PinoutPage{Dock=DockStyle.Fill,Visible=false};content.Controls.Add(flashPage);content.Controls.Add(pinoutPage);
            var footer=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=new Padding(0)};
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,84));
            var note=Theme.Label("9600 baud  /  AUTO CHECKSUM  /  BENCH VALIDATION PENDING",8.5f,Theme.Muted);note.Margin=new Padding(0,9,0,0);footer.Controls.Add(note);
            cancel=Button("Cancel",80);cancel.Height=28;cancel.Visible=false;footer.Controls.Add(cancel);shell.Controls.Add(footer);
            Controls.Add(shell);Shown+=(s,e)=>Theme.Chrome(this);
            flashNav.Click+=(s,e)=>ShowPage(false);pinoutsNav.Click+=(s,e)=>ShowPage(true);
            themeToggle.Click+=(s,e)=>{Theme.SetDark(!Theme.IsDark,true);ApplyTheme();};
            refresh.Click+=(s,e)=>RefreshPorts();
            connect.Click+=async(s,e)=>await Connect();read.Click+=async(s,e)=>await ReadEcu();write.Click+=async(s,e)=>await WriteEcu();cancel.Click+=(s,e)=>{if(cancellation!=null)cancellation.Cancel();};
            FormClosing+=(s,e)=>{if(busy){e.Cancel=true;if(!writing&&cancellation!=null)cancellation.Cancel();else Prompt.Show(this,"Wait for writing and verification to finish. Keep ECU power connected.","Write in progress",MessageBoxButtons.OK,MessageBoxIcon.Information);}else Disconnect();};
            RefreshPorts();SetBusy(false,false);ShowPage(false);ApplyTheme();
        }
        void ShowPage(bool pins){
            content.SuspendLayout();flashPage.Visible=!pins;pinoutPage.Visible=pins;
            (pins?pinoutPage:flashPage).BringToFront();content.ResumeLayout();
            flashNav.Selected=!pins;pinoutsNav.Selected=pins;flashNav.Invalidate();pinoutsNav.Invalidate();
        }
        void ApplyTheme(){Theme.Apply(this);themeToggle.Text=Theme.IsDark?"Light mode":"Dark mode";}
        static Button Button(string text,int width){return new ModernButton{Text=text,Width=width,Height=34,Margin=new Padding(0,0,8,0)};}
        void RefreshPorts(){string old=ports.SelectedItem as string;ports.Items.Clear();ports.Items.AddRange(SerialPort.GetPortNames().OrderBy(p=>p).Cast<object>().ToArray());if(ports.Items.Count>0)ports.SelectedIndex=Math.Max(0,ports.Items.IndexOf(old??""));connect.Enabled=ports.Items.Count>0;}
        void SetBusy(bool value,bool writeOperation){busy=value;writing=value&&writeOperation;ports.Enabled=refresh.Enabled=!value&&client==null;connect.Enabled=!value&&(client!=null||ports.Items.Count>0);read.Enabled=write.Enabled=!value&&client!=null&&client.Connected;cancel.Visible=value&&!writeOperation;pinoutsNav.Enabled=!value;}
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
