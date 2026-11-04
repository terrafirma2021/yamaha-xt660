using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Reflection;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace Xt660 {
    public sealed class PinSlot {public string position,row,wire,signal;public int column;}
    public sealed class PinSource {public string view,note;}
    public sealed class PinFamily {public int positions,columns;public PinSlot[] slots;public PinSource source;}
    public sealed class PinData {public Dictionary<string,PinFamily> families;}
    public sealed class PinoutPage : UserControl {
        readonly PinData data;readonly ConnectorDrawing drawing;readonly Label view;
        public PinoutPage(){
            AccessibleName="Pinouts page";Font=Theme.Body(10);AutoScaleMode=AutoScaleMode.Inherit;
            using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Xt660.Connections.json"))using(var reader=new StreamReader(stream))data=new JavaScriptSerializer().Deserialize<PinData>(reader.ReadToEnd());
            var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(0,16,0,0),ColumnCount=1,RowCount=6,Margin=new Padding(0)};
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,42));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,28));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,48));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,130));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,42));
            var selector=new ModernCombo{Width=220,AccessibleName="ECU connector type"};selector.Items.AddRange(new object[]{"26-pin ECU","34-pin ECU"});
            layout.Controls.Add(selector);
            var heading=Theme.Label("ECU CONNECTOR  /  +12V · GND · K-LINE",10,Theme.Ink);heading.Dock=DockStyle.Fill;layout.Controls.Add(heading);
            drawing=new ConnectorDrawing{Dock=DockStyle.Fill};layout.Controls.Add(drawing);
            view=Theme.Label("",9,Theme.Muted);view.Dock=DockStyle.Fill;view.AutoSize=false;layout.Controls.Add(view);
            layout.Controls.Add(new KklDrawing{Dock=DockStyle.Fill});
            var note=Theme.Label("Use a fused external 12V supply and shared ground. USB does not power the ECU.\r\nU/L labels are drawing positions, not Yamaha cavity numbers. Check the connector view before wiring.",9,Theme.Muted);note.Dock=DockStyle.Fill;note.AutoSize=false;layout.Controls.Add(note);
            selector.SelectedIndexChanged+=(s,e)=>{drawing.Family=data.families[selector.SelectedIndex==0?"early":"late"];view.Text=drawing.Family.source.view+"\r\n"+(selector.SelectedIndex==1?"The source does not establish mating-face versus wire-entry view. Confirm the physical orientation.":"26-position reference; match the physical connector. Wire labels follow the website's manual overlay.");drawing.Invalidate();};
            Controls.Add(layout);selector.SelectedIndex=0;
        }
    }
    public sealed class ConnectorDrawing : Control {
        public PinFamily Family;
        public ConnectorDrawing(){DoubleBuffered=true;AccessibleName="ECU connector drawing";}
        public static Color Signal(string name){return name=="power"?Color.FromArgb(188,41,60):name=="kline"?Color.FromArgb(242,197,0):Color.FromArgb(72,82,101);}
        protected override void OnPaint(PaintEventArgs e){
            base.OnPaint(e);if(Family==null)return;var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;
            float width=Family.columns*75+64,scale=Math.Min(ClientSize.Width/width,ClientSize.Height/225f);
            g.TranslateTransform((ClientSize.Width-width*scale)/2,0);g.ScaleTransform(scale,scale);
            using(var background=new SolidBrush(Theme.Surface))g.FillRectangle(background,0,0,width,225);
            using(var pen=new Pen(Theme.Muted,3))g.DrawLines(pen,new[]{new PointF(width/2-25,47),new PointF(width/2-25,32),new PointF(width/2+25,32),new PointF(width/2+25,47)});
            using(var coordinate=Theme.Body(12))using(var wire=Theme.Body(17))using(var centered=new StringFormat{Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center}) {
                foreach(var slot in Family.slots){float x=32+(slot.column-1)*75,y=slot.row=="Upper"?52:130;
                    bool marked=!string.IsNullOrEmpty(slot.signal);Color color=marked?Signal(slot.signal):Theme.Hover;
                    using(var brush=new SolidBrush(color))g.FillRectangle(brush,x,y,72,68);
                    using(var pen=new Pen(marked?color:Theme.Line,marked?3:1))g.DrawRectangle(pen,x,y,72,68);
                    using(var text=new SolidBrush(slot.signal=="kline"?Color.FromArgb(18,24,34):marked?Color.White:Theme.Ink)){
                        g.DrawString(slot.position,coordinate,text,new RectangleF(x,y+5,72,22),centered);
                        g.DrawString(string.IsNullOrEmpty(slot.wire)?"×":slot.wire,wire,text,new RectangleF(x,y+28,72,34),centered);
                    }
                }
            }
        }
    }
    public sealed class KklDrawing : Control {
        public KklDrawing(){DoubleBuffered=true;AccessibleName="ECU to USB KKL wiring";}
        protected override void OnPaint(PaintEventArgs e){
            base.OnPaint(e);var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=TextRenderingHint.AntiAliasGridFit;
            using(var text=new SolidBrush(Theme.Ink))using(var title=Theme.Body(9))g.DrawString("ECU → USB KKL / OBD BREAKOUT → COMPUTER",title,text,0,0);
            string[] signals={"power","ground","kline"},left={"U03  ·  +12V  (R)","U07  ·  GND  (B/W)","U12  ·  K-line  (Y/L)"},right={"OBD 16  ·  +12V","OBD 4 / 5  ·  GND","OBD 7  ·  K-line"};
            for(int i=0;i<3;i++){int y=32+i*29;using(var pen=new Pen(ConnectorDrawing.Signal(signals[i]),3))g.DrawLine(pen,185,y+9,ClientSize.Width-185,y+9);
                using(var text=new SolidBrush(Theme.Ink)){g.DrawString(left[i],Font,text,0,y);g.DrawString(right[i],Font,text,ClientSize.Width-175,y);}}
        }
    }
}
