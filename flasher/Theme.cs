using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Xt660 {
    public static class Theme {
        public static bool IsDark { get; private set; }
        public static Color Background { get { return IsDark ? Color.FromArgb(10,15,24) : Color.FromArgb(245,247,251); } }
        public static Color Surface { get { return IsDark ? Color.FromArgb(19,28,43) : Color.White; } }
        public static Color Line { get { return IsDark ? Color.FromArgb(39,53,75) : Color.FromArgb(211,219,232); } }
        public static Color Ink { get { return IsDark ? Color.FromArgb(237,242,251) : Color.FromArgb(23,34,53); } }
        public static Color Muted { get { return IsDark ? Color.FromArgb(151,168,194) : Color.FromArgb(83,101,126); } }
        public static Color Disabled { get { return IsDark ? Color.FromArgb(116,134,160) : Color.FromArgb(121,133,153); } }
        public static Color Hover { get { return IsDark ? Color.FromArgb(27,40,60) : Color.FromArgb(230,236,249); } }
        public static Color Accent { get { return IsDark ? Color.FromArgb(151,173,255) : Blue; } }
        public static readonly Color Blue=Color.FromArgb(47,82,255);
        static readonly PrivateFontCollection fonts=new PrivateFontCollection();
        static readonly string preference=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"XT660","theme.txt");
        [DllImport("gdi32.dll")] static extern IntPtr AddFontMemResourceEx(IntPtr data,uint size,IntPtr reserved,ref uint count);
        static Theme(){
            IsDark=true;
            foreach(string name in new[]{"Barlow-Regular.ttf","Barlow-SemiBold.ttf","BarlowCondensed-ExtraBoldItalic.ttf"}){
                using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Xt660."+name)){
                    if(stream==null)continue;
                    var bytes=new byte[stream.Length];stream.Read(bytes,0,bytes.Length);
                    // Both drawing and native text controls need the embedded face.
                    // Font data stays allocated for this process's lifetime.
                    var memory=Marshal.AllocCoTaskMem(bytes.Length);Marshal.Copy(bytes,0,memory,bytes.Length);
                    fonts.AddMemoryFont(memory,bytes.Length);
                    uint count=0;AddFontMemResourceEx(memory,(uint)bytes.Length,IntPtr.Zero,ref count);
                }
            }
        }
        public static void LoadPreference(){try { if(File.Exists(preference))IsDark=File.ReadAllText(preference).Trim()!="light"; }catch(IOException){}catch(UnauthorizedAccessException){}}
        public static void SetDark(bool dark,bool remember){
            IsDark=dark;if(!remember)return;
            try { Directory.CreateDirectory(Path.GetDirectoryName(preference));File.WriteAllText(preference,dark?"dark":"light"); }catch(IOException){}catch(UnauthorizedAccessException){}
        }
        public static void Apply(Control root){
            string role=root.Tag as string;
            root.BackColor=(role=="log"||root is ComboBox)?Surface:Background;
            root.ForeColor=(role=="muted"||role=="log")?Muted:Ink;
            foreach(Control child in root.Controls)Apply(child);
            root.Invalidate();var form=root as Form;if(form!=null&&form.IsHandleCreated)Chrome(form);
        }
        public static Font Body(float size){foreach(var family in fonts.Families)if(family.Name=="Barlow")return new Font(family,size,FontStyle.Regular);return new Font("Segoe UI",size);}
        public static Font Display(float size){foreach(var family in fonts.Families)if(family.Name.Contains("Condensed"))return new Font(family,size,family.IsStyleAvailable(FontStyle.Bold|FontStyle.Italic)?FontStyle.Bold|FontStyle.Italic:family.IsStyleAvailable(FontStyle.Italic)?FontStyle.Italic:FontStyle.Regular);return new Font("Arial",size,FontStyle.Bold|FontStyle.Italic);}
        public static Label Label(string text,float size,Color color){return new Label{Text=text,Font=Body(size),ForeColor=color,Tag=color==Muted?"muted":null,BackColor=Color.Transparent,AutoSize=true,UseCompatibleTextRendering=true};}
        public static GraphicsPath Round(RectangleF r,float radius){var p=new GraphicsPath();float d=radius*2;p.AddArc(r.X,r.Y,d,d,180,90);p.AddArc(r.Right-d,r.Y,d,d,270,90);p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);p.AddArc(r.X,r.Bottom-d,d,d,90,90);p.CloseFigure();return p;}
        [DllImport("dwmapi.dll")]static extern int DwmSetWindowAttribute(IntPtr window,int attribute,ref int value,int size);
        public static void Chrome(Form form){try{int dark=IsDark?1:0;DwmSetWindowAttribute(form.Handle,20,ref dark,4);int background=ColorTranslator.ToWin32(Background);DwmSetWindowAttribute(form.Handle,35,ref background,4);int ink=ColorTranslator.ToWin32(Ink);DwmSetWindowAttribute(form.Handle,36,ref ink,4);}catch(DllNotFoundException){}catch(EntryPointNotFoundException){}}
    }
    public sealed class BrandHeader : Control {
        readonly Image logo;
        public BrandHeader(){DoubleBuffered=true;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Xt660.Logo.png"))if(stream!=null)using(var decoded=Image.FromStream(stream))logo=new Bitmap(decoded);AccessibleName="Yamaha XT660 ECU Flash Tool";}
        protected override void OnPaint(PaintEventArgs e){
            base.OnPaint(e);var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;
            if(logo!=null)using(var attributes=new ImageAttributes()){
                Color ink=Theme.Ink;
                attributes.SetColorMatrix(new ColorMatrix(new[]{new float[]{0,0,0,0,0},new float[]{0,0,0,0,0},new float[]{0,0,0,0,0},new float[]{0,0,0,1,0},new float[]{ink.R/255f,ink.G/255f,ink.B/255f,0,1}}));
                g.DrawImage(logo,new Rectangle(0,8,138,49),0,0,logo.Width,logo.Height,GraphicsUnit.Pixel,attributes);
            }
            using(var pen=new Pen(Theme.Line))g.DrawLine(pen,158,9,158,57);
            using(var font=Theme.Display(26))using(var ink=new SolidBrush(Theme.Ink))g.DrawString("XT660",font,ink,175,0);
            using(var font=Theme.Body(8))using(var muted=new SolidBrush(Theme.Muted))g.DrawString("ECU FLASH TOOL",font,muted,181,43);
        }
        protected override void Dispose(bool disposing){if(disposing&&logo!=null)logo.Dispose();base.Dispose(disposing);}
    }
    public class ModernButton : Button {
        public bool Primary,ActionCard,Navigation,Selected;public string Subtitle="";bool hover;
        public ModernButton(){FlatStyle=FlatStyle.Flat;FlatAppearance.BorderSize=0;Cursor=Cursors.Hand;Font=Theme.Body(10.5f);SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);}
        protected override void OnMouseEnter(EventArgs e){hover=true;Invalidate();base.OnMouseEnter(e);}
        protected override void OnMouseLeave(EventArgs e){hover=false;Invalidate();base.OnMouseLeave(e);}
        protected override void OnPaint(PaintEventArgs e){
            var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;g.Clear(Parent==null?Theme.Background:Parent.BackColor);
            if(Navigation){
                if(hover&&Enabled)using(var brush=new SolidBrush(Theme.Hover))g.FillRectangle(brush,0,0,Width,Height);
                using(var pen=new Pen(Selected?Theme.Blue:Theme.Line,Selected?3:1))g.DrawLine(pen,0,Height-2,Width,Height-2);
                using(var format=new StringFormat{Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center})using(var brush=new SolidBrush(!Enabled?Theme.Disabled:Selected?Theme.Accent:Theme.Muted))g.DrawString(Text,Font,brush,new RectangleF(0,0,Width,Height-4),format);
                if(Focused)ControlPaint.DrawFocusRectangle(g,new Rectangle(5,5,Width-10,Height-13),Theme.Ink,Theme.Background);
                return;
            }
            Color fill=Primary&&Enabled?Theme.Blue:Theme.Surface;if(hover&&Enabled)fill=Primary?Color.FromArgb(68,101,255):Theme.Hover;
            using(var shape=Theme.Round(new RectangleF(1,1,Width-3,Height-3),6))using(var brush=new SolidBrush(fill))using(var line=new Pen(Focused&&Enabled?Theme.Blue:Theme.Line,Focused&&Enabled?2:1)){g.FillPath(brush,shape);g.DrawPath(line,shape);}
            Color text=!Enabled?Theme.Disabled:Primary?Color.White:Theme.Ink;
            if(ActionCard){
                using(var title=Theme.Display(19))using(var brush=new SolidBrush(text))g.DrawString(Text,title,brush,20,12);
                using(var detail=Theme.Body(10))using(var brush=new SolidBrush(Enabled?Theme.Muted:Theme.Disabled))g.DrawString(Subtitle,detail,brush,22,48);
                float x=Width-36,y=35;using(var pen=new Pen(text,1.5f)){g.DrawLine(pen,x-7,y,x+7,y);g.DrawLines(pen,new[]{new PointF(x+2,y-5),new PointF(x+7,y),new PointF(x+2,y+5)});}
            }else using(var format=new StringFormat{Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center})using(var brush=new SolidBrush(text))g.DrawString(Text,Font,brush,new RectangleF(0,0,Width,Height),format);
        }
    }
    public sealed class ModernCombo : ComboBox {
        public ModernCombo(){DropDownStyle=ComboBoxStyle.DropDownList;DrawMode=DrawMode.OwnerDrawFixed;FlatStyle=FlatStyle.Flat;Font=Theme.Body(10.5f);ItemHeight=24;}
        protected override void OnDrawItem(DrawItemEventArgs e){
            e.Graphics.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;
            using(var background=new SolidBrush((e.State&DrawItemState.Selected)!=0?Theme.Hover:Theme.Surface))e.Graphics.FillRectangle(background,e.Bounds);
            if(e.Index>=0)using(var brush=new SolidBrush(Enabled?Theme.Ink:Theme.Disabled))e.Graphics.DrawString(GetItemText(Items[e.Index]),Font,brush,e.Bounds.Left+9,e.Bounds.Top+3);
        }
        protected override void WndProc(ref Message m){
            base.WndProc(ref m);if(m.Msg!=0x000F)return;
            using(var g=Graphics.FromHwnd(Handle))using(var fill=new SolidBrush(Theme.Surface))using(var ink=new SolidBrush(Enabled?Theme.Muted:Theme.Disabled))using(var border=new Pen(Theme.Line)){
                int right=ClientSize.Width,mid=ClientSize.Height/2;
                g.FillRectangle(fill,right-23,1,22,ClientSize.Height-2);
                g.FillPolygon(ink,new[]{new Point(right-16,mid-2),new Point(right-8,mid-2),new Point(right-12,mid+2)});
                g.DrawRectangle(border,0,0,right-1,ClientSize.Height-1);
            }
        }
    }
    public sealed class ThinProgress : Control {
        int value;public int Value{get{return value;}set{this.value=Math.Max(0,Math.Min(100,value));Invalidate();}}
        public ThinProgress(){DoubleBuffered=true;Height=5;AccessibleName="Operation progress";}
        protected override void OnPaint(PaintEventArgs e){using(var bg=new SolidBrush(Theme.Line))e.Graphics.FillRectangle(bg,0,0,Width,Height);using(var fg=new SolidBrush(Theme.Blue))e.Graphics.FillRectangle(fg,0,0,Width*value/100f,Height);}
    }
    public static class Prompt {
        public static DialogResult Show(IWin32Window owner,string message,string title,MessageBoxButtons buttons=MessageBoxButtons.OK,MessageBoxIcon icon=MessageBoxIcon.None,MessageBoxDefaultButton defaultButton=MessageBoxDefaultButton.Button1){
            using(var window=new Form{Text="XT660 · "+title,ClientSize=new Size(600,420),FormBorderStyle=FormBorderStyle.FixedDialog,StartPosition=FormStartPosition.CenterParent,Font=Theme.Body(11),MinimizeBox=false,MaximizeBox=false,ShowInTaskbar=false,ShowIcon=false}){
                var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(24),RowCount=3,ColumnCount=1};
                layout.RowStyles.Add(new RowStyle(SizeType.Absolute,48));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
                layout.Controls.Add(new Label{Text=title,Font=Theme.Display(20),Dock=DockStyle.Fill,UseCompatibleTextRendering=true});
                layout.Controls.Add(new RichTextBox{Text=message,ReadOnly=true,BorderStyle=BorderStyle.None,Tag="muted",Font=Theme.Body(11),Dock=DockStyle.Fill,ScrollBars=RichTextBoxScrollBars.Vertical,TabStop=false,DetectUrls=false});
                var actions=new FlowLayoutPanel{Dock=DockStyle.Fill,FlowDirection=FlowDirection.RightToLeft};
                var ok=new ModernButton{Text=title=="Confirm write"?"Write ECU":"OK",Primary=true,Width=125,Height=36,DialogResult=DialogResult.OK};actions.Controls.Add(ok);window.AcceptButton=ok;
                if(buttons==MessageBoxButtons.OKCancel){var cancel=new ModernButton{Text="Cancel",Width=100,Height=36,DialogResult=DialogResult.Cancel,Margin=new Padding(0,0,12,0)};actions.Controls.Add(cancel);window.CancelButton=cancel;if(defaultButton==MessageBoxDefaultButton.Button2)window.Shown+=(s,e)=>cancel.Focus();}
                layout.Controls.Add(actions);window.Controls.Add(layout);Theme.Apply(window);window.Shown+=(s,e)=>Theme.Chrome(window);
                return window.ShowDialog(owner);
            }
        }
    }
}
