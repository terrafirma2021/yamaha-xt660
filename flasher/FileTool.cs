using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Xml;

namespace Xt660 {
    public class Definition {
        public string id, label, variant, bin_file, file, bin_sha256, xdf_sha256, code_family;
        public int bin_size, base_address;
    }
    public class Manifest { public int schema_version; public Definition[] definitions; }
    public class PatchEntry { public int Address; public byte[] Before, After; }
    public class Patch { public string Title; public List<PatchEntry> Entries = new List<PatchEntry>(); }
    public class Reference {
        public Definition Definition; public byte[] Bytes; public bool[] Maps;
        public List<Patch> Patches = new List<Patch>();
    }
    public class FileCheck {
        public string filename, sha256, identity, variant, family, checksum, boot;
        public int bytes, base_address; public bool matched, checksum_pass;
    }
    public sealed class Library {
        public readonly List<Reference> References = new List<Reference>();
        public static string Hash(byte[] data) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }
        static int Number(string s) { return s.StartsWith("0x",StringComparison.OrdinalIgnoreCase)?Convert.ToInt32(s.Substring(2),16):int.Parse(s); }
        static byte[] Hex(string s) {
            if(s.Length%2!=0)throw new InvalidDataException("Odd patch length");
            return Enumerable.Range(0,s.Length/2).Select(i=>Convert.ToByte(s.Substring(i*2,2),16)).ToArray();
        }
        static string ChildPath(string root,string path) {
            string full=Path.GetFullPath(Path.Combine(root,path));
            if(!full.StartsWith(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Path outside bundle");
            return full;
        }
        public Library(string root) {
            var manifest=new JavaScriptSerializer().Deserialize<Manifest>(File.ReadAllText(Path.Combine(root,"manifest.json")));
            if(manifest.schema_version!=1||manifest.definitions==null||manifest.definitions.Length==0)throw new InvalidDataException("Unsupported bundle manifest");
            foreach(var d in manifest.definitions) {
                var bytes=File.ReadAllBytes(ChildPath(root,d.bin_file));
                var xdf=File.ReadAllBytes(ChildPath(root,d.file));
                if(bytes.Length!=d.bin_size||Hash(bytes)!=d.bin_sha256||Hash(xdf)!=d.xdf_sha256)throw new InvalidDataException("Bundle hash mismatch: "+d.id);
                if(Base(bytes)!=d.base_address)throw new InvalidDataException("Invalid BIN base");
                var r=new Reference {Definition=d,Bytes=bytes,Maps=new bool[bytes.Length]};
                var doc=new XmlDocument {XmlResolver=null};
                var settings=new XmlReaderSettings {DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null};
                using(var stream=new MemoryStream(xdf))using(var reader=XmlReader.Create(stream,settings))doc.Load(reader);
                if(doc.SelectSingleNode("/XDFFORMAT/XDFHEADER/BASEOFFSET").Attributes["offset"].Value!="0")throw new InvalidDataException("XDF base is not zero");
                foreach(XmlNode node in doc.SelectNodes("/XDFFORMAT/XDFTABLE/XDFAXIS[@id='z']/EMBEDDEDDATA")) {
                    int start=Number(node.Attributes["mmedaddress"].Value);
                    int count=checked(int.Parse(node.Attributes["mmedrowcount"].Value)*int.Parse(node.Attributes["mmedcolcount"].Value)*int.Parse(node.Attributes["mmedelementsizebits"].Value)/8);
                    if(start<0x1800-d.base_address||start+count>0xF800-d.base_address)throw new InvalidDataException("Map outside application");
                    for(int n=start;n<start+count;n++)r.Maps[n]=true;
                }
                foreach(XmlNode node in doc.SelectNodes("/XDFFORMAT/XDFPATCH")) {
                    var p=new Patch {Title=node.SelectSingleNode("title").InnerText};
                    foreach(XmlNode e in node.SelectNodes("XDFPATCHENTRY")) {
                        var entry=new PatchEntry {Address=Number(e.Attributes["address"].Value),Before=Hex(e.Attributes["basedata"].Value),After=Hex(e.Attributes["patchdata"].Value)};
                        int count=Number(e.Attributes["datasize"].Value);
                        if(count<=0||count!=entry.Before.Length||count!=entry.After.Length||entry.Address<0x1800-d.base_address||entry.Address+count>0xF7FC-d.base_address)throw new InvalidDataException("Invalid patch bounds");
                        p.Entries.Add(entry);
                    }
                    if(p.Entries.Count==0)throw new InvalidDataException("Empty patch");
                    r.Patches.Add(p);
                }
                if(!ChecksumAnchors(bytes,d))throw new InvalidDataException("Checksum instructions do not match: "+d.id);
                References.Add(r);
            }
        }
        public static int Base(byte[] data) {
            if(data.Length==65536)return 0;if(data.Length==59392)return 0x1800;
            throw new InvalidDataException("Expected a 65,536-byte or 59,392-byte BIN. Files are never padded or truncated.");
        }
        public static int Sum(byte[] data) {
            int b=Base(data),sum=0;for(int a=0x1800-b;a<0xF800-b;a+=2)sum=(sum+(data[a]<<8)+data[a+1])&65535;return sum;
        }
        static bool EqualsAt(byte[] bytes,int at,byte[] expected) {
            return at>=0&&at+expected.Length<=bytes.Length&&expected.Select((b,i)=>bytes[at+i]==b).All(b=>b);
        }
        static bool ChecksumAnchors(byte[] data,Definition d) {
            bool early=d.code_family=="early";
            if(!early&&d.code_family!="late")return false;
            return EqualsAt(data,(early?0x5358:0x4B65)-d.base_address,Hex(early?"ccf7ff16a489":"ccf7ff16971d"))
                &&EqualsAt(data,(early?0xA489:0x971D)-d.base_address,Hex(early?"4df080165fa47c0ddece180087c7e3003431b7c6841f8c1000b7c62603165fa408082705be0dde23e5b7c6c6008daa552702c6ff":"4df0801656b17c0e62ce180087c7e3003431b7c6841f8c1000b7c626031656b108082705be0e6223e5b7c6c6008daa552702c6ff"))
                &&EqualsAt(data,0xF7FE-d.base_address,Hex("5aa5"));
        }
        public static bool PatchMatches(byte[] bytes,Patch p,bool applied) {
            return p.Entries.All(e=>EqualsAt(bytes,e.Address,applied?e.After:e.Before));
        }
        public bool Matches(byte[] data,Reference r) {
            if(data.Length!=r.Bytes.Length||!ChecksumAnchors(data,r.Definition))return false;
            var allowed=(bool[])r.Maps.Clone();int b=r.Definition.base_address;
            allowed[0xF7FC-b]=allowed[0xF7FD-b]=true;
            foreach(var p in r.Patches)if(PatchMatches(data,p,false)||PatchMatches(data,p,true))
                foreach(var e in p.Entries)for(int n=0;n<e.Before.Length;n++)if(e.Before[n]!=e.After[n])allowed[e.Address+n]=true;
            return data.Select((v,n)=>v==r.Bytes[n]||allowed[n]).All(v=>v);
        }
        public Reference Identify(byte[] bytes) {
            string hash=Hash(bytes);
            return References.FirstOrDefault(r=>r.Definition.bin_sha256==hash)??References.FirstOrDefault(r=>Matches(bytes,r));
        }
        public FileCheck Inspect(byte[] bytes,string name) {
            int b=Base(bytes),sum=Sum(bytes);var r=Identify(bytes);
            return new FileCheck {filename=name,sha256=Hash(bytes),bytes=bytes.Length,base_address=b,matched=r!=null,
                identity=r==null?"Unrecognised BIN":r.Definition.label,variant=r==null?"":r.Definition.variant,family=r==null?null:r.Definition.code_family,
                checksum="0x"+sum.ToString("X4"),checksum_pass=r!=null&&sum==0xAA55,
                boot=bytes.Skip(0xF800-b).All(v=>v==255)?"FF placeholder; boot not captured":"Populated"};
        }
        public byte[] CorrectCopy(byte[] input) {
            var r=Identify(input);if(r==null)throw new InvalidDataException("Unrecognised code or incomplete patch; checksum saving is unavailable.");
            var copy=(byte[])input.Clone();int o=0xF7FC-Base(copy);
            int word=((copy[o]<<8)+copy[o+1]+0xAA55-Sum(copy))&65535;
            copy[o]=(byte)(word>>8);copy[o+1]=(byte)word;
            if(Sum(copy)!=0xAA55)throw new InvalidDataException("Checksum verification failed");return copy;
        }
        public void SaveCopy(byte[] bytes,string input,string output) {
            string target=Path.GetFullPath(output);
            if(string.Equals(target,Path.GetFullPath(input),StringComparison.OrdinalIgnoreCase))throw new IOException("Choose a new filename; the opened BIN is preserved.");
            if(File.Exists(target)&&References.Any(r=>Hash(File.ReadAllBytes(target))==r.Definition.bin_sha256))throw new IOException("Do not overwrite a registered source BIN.");
            var fixedBytes=CorrectCopy(bytes);File.WriteAllBytes(target,fixedBytes);
            if(!File.ReadAllBytes(target).SequenceEqual(fixedBytes))throw new IOException("Saved file verification failed");
        }
    }
    public sealed class MainWindow : Form {
        readonly Library library; readonly TextBox report; readonly Button save,compare;
        byte[] opened; string path;
        public MainWindow(Library lib) {
            library=lib;Text="XT660 File Tool";MinimumSize=new Size(720,480);Size=new Size(840,610);StartPosition=FormStartPosition.CenterScreen;
            Font=new Font("Segoe UI",10);BackColor=Color.FromArgb(245,246,249);
            var layout=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(24),ColumnCount=1,RowCount=4};
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,50));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,54));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,52));
            layout.Controls.Add(new Label {Text="XT660  /  BIN files",Font=new Font("Segoe UI",20,FontStyle.Bold),Dock=DockStyle.Fill});
            var buttons=new FlowLayoutPanel {Dock=DockStyle.Fill,WrapContents=false};
            var open=new Button {Text="Open BIN",AutoSize=true,Height=36};save=new Button {Text="Save checksum copy",AutoSize=true,Height=36,Enabled=false};compare=new Button {Text="Compare file",AutoSize=true,Height=36,Enabled=false};
            buttons.Controls.AddRange(new Control[]{open,save,compare});layout.Controls.Add(buttons);
            report=new TextBox {Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill,Font=new Font("Consolas",10),BackColor=Color.White,Text="Open a BIN to check its identity and startup checksum.\r\n\r\nEdit maps and features in TunerPro using the matching XDF.\r\nThen open the saved file here and save a checksum-corrected copy."};layout.Controls.Add(report);
            layout.Controls.Add(new Label {Text="File tools preview. ECU connection, reading and flashing are not implemented.\r\nNo COM port is opened and no bytes are sent to an ECU.",Dock=DockStyle.Fill,Padding=new Padding(0,10,0,0),ForeColor=Color.DimGray});Controls.Add(layout);
            open.Click+=(s,e)=>Run(()=>{using(var d=new OpenFileDialog {Filter="BIN files|*.bin|All files|*.*",InitialDirectory=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"bins")})if(d.ShowDialog()==DialogResult.OK){var candidate=File.ReadAllBytes(d.FileName);var check=library.Inspect(candidate,d.FileName);opened=candidate;path=d.FileName;save.Enabled=check.matched;compare.Enabled=true;report.Text=Format(check);}});
            save.Click+=(s,e)=>Run(()=>{using(var d=new SaveFileDialog {Filter="BIN files|*.bin",FileName=Path.GetFileNameWithoutExtension(path)+"-checksum-fixed.bin",InitialDirectory=Path.GetDirectoryName(path)})if(d.ShowDialog()==DialogResult.OK){library.SaveCopy(opened,path,d.FileName);report.Text+="\r\nSaved and verified: "+d.FileName+"\r\nStartup checksum: 0xAA55. Original file unchanged.\r\n";}});
            compare.Click+=(s,e)=>Run(()=>{using(var d=new OpenFileDialog {Filter="BIN files|*.bin|All files|*.*"})if(d.ShowDialog()==DialogResult.OK){var other=File.ReadAllBytes(d.FileName);report.Text+="\r\n"+Compare(opened,other)+"\r\n";}});
        }
        void Run(Action action) {try{action();}catch(Exception ex){MessageBox.Show(this,ex.Message,"File check",MessageBoxButtons.OK,MessageBoxIcon.Error);}}
        static string Format(FileCheck c) {return c.filename+"\r\n\r\n"+c.identity+" / "+c.variant+"\r\n"+c.bytes+" bytes; CPU base 0x"+c.base_address.ToString("X4")+"\r\nStartup checksum: "+c.checksum+(c.matched?" (expected 0xAA55)":" (profile unverified)")+"\r\nBoot: "+c.boot+"\r\n\r\nSHA-256\r\n"+c.sha256+"\r\n\r\n"+(c.matched?"Recognised map / feature layout. This does not confirm physical ECU fitment.":"Unknown code or incomplete patch. Automatic correction is unavailable.");}
        public static string Compare(byte[] a,byte[] b) {if(a.Length!=b.Length)return "Files have different lengths; not equal.";int count=a.Select((v,i)=>v!=b[i]?1:0).Sum();return count==0?"Files match byte-for-byte.":count+" bytes differ.";}
    }
    public static class Program {
        [STAThread] public static int Main(string[] args) {
            try {
                var lib=new Library(AppDomain.CurrentDomain.BaseDirectory);
                if(args.Length>0) {
                    if(args[0]=="--verify-bundle"&&args.Length==1){Console.WriteLine("Verified "+lib.References.Count+" BIN/XDF pairs");return 0;}
                    if(args[0]=="--inspect"&&args.Length==2){Console.WriteLine(new JavaScriptSerializer().Serialize(lib.Inspect(File.ReadAllBytes(args[1]),args[1])));return 0;}
                    if(args[0]=="--fix"&&args.Length==3){lib.SaveCopy(File.ReadAllBytes(args[1]),args[1],args[2]);Console.WriteLine("Saved checksum 0xAA55");return 0;}
                    if(args[0]=="--compare"&&args.Length==3){var a=File.ReadAllBytes(args[1]);var b=File.ReadAllBytes(args[2]);Console.WriteLine(MainWindow.Compare(a,b));return a.SequenceEqual(b)?0:2;}
                    throw new ArgumentException("Use --verify-bundle, --inspect FILE, --fix INPUT OUTPUT or --compare A B");
                }
                Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new MainWindow(lib));return 0;
            } catch(Exception ex) {if(args.Length>0)Console.Error.WriteLine(ex.Message);else MessageBox.Show(ex.Message,"XT660 File Tool",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        }
    }
}
