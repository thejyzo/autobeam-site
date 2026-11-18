from PIL import Image, ImageDraw, ImageFont
W,H=1200,630; S=2
im=Image.new("RGB",(W*S,H*S),"#0b0b0d"); d=ImageDraw.Draw(im)
AMB="#ffc21a"
M="/usr/share/fonts/truetype/google-fonts/ofl/montserrat/Montserrat[wght].ttf"
I="/usr/share/fonts/opentype/inter/"
def mf(sz,w):
    f=ImageFont.truetype(M,sz*S); f.set_variation_by_axes([w]); return f
# soft amber glow, right
glow=Image.new("L",(W*S,H*S),0); g=ImageDraw.Draw(glow)
for r in range(520,0,-8):
    g.ellipse([(980-r)*S,(300-r)*S,(980+r)*S,(300+r)*S],fill=int(38*(1-r/520)))
im.paste(Image.new("RGB",im.size,AMB),(0,0),glow)
# logo mark (as favicon), right side
ox,oy,k=850,215,4.2   # favicon 64-grid -> px
def P(x,y): return ((ox+(x-6)*k)*S,(oy+(y-20)*k)*S)
d.pieslice([P(6,20)[0]-0,P(6,20)[1],P(46,44)[0],P(46,44)[1]],90,270,fill="#ffffff")
d.rectangle([P(18,20),P(30,44)],fill="#ffffff")
for y0,x1 in [(22,58),(31,60),(40,56)]:
    d.polygon([P(34,y0),P(x1,y0),P(x1-4,y0+5),P(34,y0+5)],fill=AMB)
# text
x=80*S
d.text((x,96*S),"ФАРИ · ЛІХТАРІ · ДХО",font=mf(24,700),fill=AMB)
f=mf(92,800)
d.text((x,150*S),"Auto",font=f,fill="#ffffff")
d.text((x+d.textlength("Auto",font=f),150*S),"Beam",font=f,fill=AMB)
sub=mf(40,700)
d.text((x,290*S),"Оригінальна оптика",font=sub,fill="#ffffff")
d.text((x,342*S),"зі США для вашого авто",font=sub,fill="#ffffff")
# chips
cf=ImageFont.truetype(I+"Inter-SemiBold.otf",24*S); cx=x
for t in ["Оригінал","Гарантія 14 днів","Підбір за VIN"]:
    w=d.textlength(t,font=cf)+44*S
    d.rounded_rectangle([cx,440*S,cx+w,492*S],radius=26*S,outline="#3a3a40",width=2*S,fill="#16161a")
    d.text((cx+22*S,452*S),t,font=cf,fill="#e8e8ea"); cx+=w+14*S
d.text((x,540*S),"autobeam.com.ua",font=ImageFont.truetype(I+"Inter-Medium.otf",26*S),fill="#9a9aa2")
im.resize((W,H),Image.LANCZOS).save("src/assets/og.png",optimize=True)
