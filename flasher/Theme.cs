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
        public static readonly Color Background=Color.FromArgb(10,15,24),Surface=Color.FromArgb(19,28,43),Line=Color.FromArgb(39,53,75),Ink=Color.FromArgb(237,242,251),Muted=Color.FromArgb(151,168,194),Blue=Color.FromArgb(47,82,255);
        static readonly PrivateFontCollection fonts=new PrivateFontCollection();
        static Theme(){
            foreach(string name in new[]{"Barlow-Regular.ttf","Barlow-SemiBold.ttf","BarlowCondensed-ExtraBoldItalic.ttf"}){
                using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Xt660."+name)){
                    if(stream==null)continue;var bytes=new byte[stream.Length];stream.Read(bytes,0,bytes.Length);
                    // GDI+ retains memory-font data for the lifetime of the collection.
                    var memory=Marshal.AllocCoTaskMem(bytes.Length);Marshal.Copy(bytes,0,memory,bytes.Length);fonts.AddMemoryFont(memory,bytes.Length);
                }
            }
        }
        public static Font Body(float size){foreach(var family in fonts.Families)if(family.Name=="Barlow")return new Font(family,size,FontStyle.Regular);return new Font("Segoe UI",size);}
        public static Font Display(float size){foreach(var family in fonts.Families)if(family.Name.Contains("Condensed"))return new Font(family,size,family.IsStyleAvailable(FontStyle.Bold|FontStyle.Italic)?FontStyle.Bold|FontStyle.Italic:family.IsStyleAvailable(FontStyle.Italic)?FontStyle.Italic:FontStyle.Regular);return new Font("Arial",size,FontStyle.Bold|FontStyle.Italic);}
        public static Label Label(string text,float size,Color color){return new Label{Text=text,Font=Body(size),ForeColor=color,BackColor=Color.Transparent,AutoSize=true};}
        public static GraphicsPath Round(RectangleF r,float radius){var p=new GraphicsPath();float d=radius*2;p.AddArc(r.X,r.Y,d,d,180,90);p.AddArc(r.Right-d,r.Y,d,d,270,90);p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);p.AddArc(r.X,r.Bottom-d,d,d,90,90);p.CloseFigure();return p;}
        [DllImport("dwmapi.dll")]static extern int DwmSetWindowAttribute(IntPtr window,int attribute,ref int value,int size);
        public static void Chrome(Form form){try{int dark=1;DwmSetWindowAttribute(form.Handle,20,ref dark,4);int background=ColorTranslator.ToWin32(Background);DwmSetWindowAttribute(form.Handle,35,ref background,4);}catch(DllNotFoundException){}catch(EntryPointNotFoundException){}}
    }
    public sealed class BrandHeader : Control {
        readonly Image logo;
        public BrandHeader(){DoubleBuffered=true;BackColor=Theme.Background;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Xt660.Logo.png"))if(stream!=null)using(var decoded=Image.FromStream(stream))logo=new Bitmap(decoded);AccessibleName="Yamaha XT660 ECU Flash Tool";}
        protected override void OnPaint(PaintEventArgs e){base.OnPaint(e);var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;
            if(logo!=null)using(var attributes=new ImageAttributes()){
                attributes.SetColorMatrix(new ColorMatrix(new[]{new float[]{0,0,0,0,0},new float[]{0,0,0,0,0},new float[]{0,0,0,0,0},new float[]{0,0,0,1,0},new float[]{1,1,1,0,1}}));
                g.DrawImage(logo,new Rectangle(0,14,177,63),0,0,logo.Width,logo.Height,GraphicsUnit.Pixel,attributes);
            }
            using(var pen=new Pen(Theme.Line))g.DrawLine(pen,199,18,199,76);
            using(var font=Theme.Display(37))using(var ink=new SolidBrush(Theme.Ink))g.DrawString("XT660",font,ink,218,0);
            using(var font=Theme.Body(9))using(var muted=new SolidBrush(Theme.Muted))g.DrawString("ECU FLASH TOOL",font,muted,226,61);
            using(var pen=new Pen(Theme.Line))g.DrawLine(pen,0,97,Width,97);
            using(var pen=new Pen(Theme.Blue,3))g.DrawLine(pen,0,97,68,97);
        }
        protected override void Dispose(bool disposing){if(disposing&&logo!=null)logo.Dispose();base.Dispose(disposing);}
    }
    public class ModernButton : Button {
        public bool Primary,ActionCard;public string Subtitle="";bool hover;
        public ModernButton(){FlatStyle=FlatStyle.Flat;FlatAppearance.BorderSize=0;Cursor=Cursors.Hand;Font=Theme.Body(11);SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);}
        protected override void OnMouseEnter(EventArgs e){hover=true;Invalidate();base.OnMouseEnter(e);}
        protected override void OnMouseLeave(EventArgs e){hover=false;Invalidate();base.OnMouseLeave(e);}
        protected override void OnPaint(PaintEventArgs e){
            var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;g.Clear(Parent==null?Theme.Background:Parent.BackColor);
            Color fill=Primary&&Enabled?Theme.Blue:Theme.Surface;if(hover&&Enabled)fill=Primary?Color.FromArgb(68,101,255):Color.FromArgb(27,40,60);
            using(var shape=Theme.Round(new RectangleF(1,1,Width-3,Height-3),7))using(var brush=new SolidBrush(fill))using(var line=new Pen(Focused&&Enabled?Theme.Blue:Theme.Line,Focused&&Enabled?2:1)){g.FillPath(brush,shape);g.DrawPath(line,shape);}
            Color text=Enabled?Theme.Ink:Color.FromArgb(122,141,168);
            if(ActionCard){
                using(var title=Theme.Display(25))using(var brush=new SolidBrush(text))g.DrawString(Text,title,brush,22,15);
                using(var detail=Theme.Body(10))using(var brush=new SolidBrush(Enabled?Theme.Muted:Color.FromArgb(106,124,150)))g.DrawString(Subtitle,detail,brush,25,61);
                float x=Width-43,y=42;using(var pen=new Pen(text,2)){g.DrawLine(pen,x-9,y,x+9,y);g.DrawLines(pen,new[]{new PointF(x+3,y-6),new PointF(x+9,y),new PointF(x+3,y+6)});}
            }else using(var format=new StringFormat{Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center})using(var brush=new SolidBrush(text))g.DrawString(Text,Font,brush,new RectangleF(0,0,Width,Height),format);
        }
    }
    public sealed class ModernCombo : ComboBox {
        public ModernCombo(){DropDownStyle=ComboBoxStyle.DropDownList;DrawMode=DrawMode.OwnerDrawFixed;FlatStyle=FlatStyle.Flat;BackColor=Theme.Surface;ForeColor=Theme.Ink;Font=Theme.Body(12);ItemHeight=29;}
        protected override void OnDrawItem(DrawItemEventArgs e){
            using(var background=new SolidBrush((e.State&DrawItemState.Selected)!=0?Color.FromArgb(34,49,74):Theme.Surface))e.Graphics.FillRectangle(background,e.Bounds);
            if(e.Index>=0)using(var brush=new SolidBrush(Theme.Ink))e.Graphics.DrawString(GetItemText(Items[e.Index]),Font,brush,e.Bounds.Left+10,e.Bounds.Top+4);
        }
    }
    public sealed class ThinProgress : Control {
        int value;public int Value{get{return value;}set{this.value=Math.Max(0,Math.Min(100,value));Invalidate();}}
        public ThinProgress(){DoubleBuffered=true;Height=5;AccessibleName="Operation progress";}
        protected override void OnPaint(PaintEventArgs e){using(var bg=new SolidBrush(Theme.Line))e.Graphics.FillRectangle(bg,0,0,Width,Height);using(var fg=new SolidBrush(Theme.Blue))e.Graphics.FillRectangle(fg,0,0,Width*value/100f,Height);}
    }
    public static class Prompt {
        public static DialogResult Show(IWin32Window owner,string message,string title,MessageBoxButtons buttons=MessageBoxButtons.OK,MessageBoxIcon icon=MessageBoxIcon.None,MessageBoxDefaultButton defaultButton=MessageBoxDefaultButton.Button1){
            using(var window=new Form{Text="XT660 · "+title,ClientSize=new Size(640,460),MinimumSize=new Size(600,440),StartPosition=FormStartPosition.CenterParent,BackColor=Theme.Background,ForeColor=Theme.Ink,Font=Theme.Body(12),MinimizeBox=false,MaximizeBox=false,ShowInTaskbar=false,ShowIcon=false}){
                var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(28),RowCount=3,ColumnCount=1};
                layout.RowStyles.Add(new RowStyle(SizeType.Absolute,58));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,48));
                layout.Controls.Add(new Label{Text=title,Font=Theme.Display(27),ForeColor=Theme.Ink,Dock=DockStyle.Fill});
                layout.Controls.Add(new TextBox{Text=message,Multiline=true,ReadOnly=true,BorderStyle=BorderStyle.None,BackColor=Theme.Background,ForeColor=Theme.Muted,Font=Theme.Body(12),Dock=DockStyle.Fill,ScrollBars=ScrollBars.Vertical,TabStop=false});
                var actions=new FlowLayoutPanel{Dock=DockStyle.Fill,FlowDirection=FlowDirection.RightToLeft};
                var ok=new ModernButton{Text=title=="Confirm write"?"Write ECU":"OK",Primary=true,Width=132,Height=40,DialogResult=DialogResult.OK};actions.Controls.Add(ok);window.AcceptButton=ok;
                if(buttons==MessageBoxButtons.OKCancel){var cancel=new ModernButton{Text="Cancel",Width=105,Height=40,DialogResult=DialogResult.Cancel,Margin=new Padding(0,0,12,0)};actions.Controls.Add(cancel);window.CancelButton=cancel;if(defaultButton==MessageBoxDefaultButton.Button2)window.Shown+=(s,e)=>cancel.Focus();}
                layout.Controls.Add(actions);window.Controls.Add(layout);window.Shown+=(s,e)=>Theme.Chrome(window);
                return window.ShowDialog(owner);
            }
        }
    }
}
