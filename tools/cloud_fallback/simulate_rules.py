import sys, re, datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from psd_tools import PSDImage
src, fontdir, outp, SIZE, DY = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5])
psd = PSDImage.open(src)
pat = re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})')
WD='月火水木金土日'
dl = [l for l in psd if l.kind=='type' and '集計期間' not in l.text and pat.search(l.text)]
ids = {l.layer_id for l in dl}
base = psd.composite(layer_filter=lambda l: l.is_visible() and l.layer_id not in ids).convert('RGBA')
SS=4
f = ImageFont.truetype(fontdir+'/NotoSansCJK-Bold.ttc', int(SIZE*SS), index=0)
for l in dl:
    y,mo,d,h,mi = map(int, pat.search(l.text).groups()); dt=datetime.datetime(y,mo,d,h,mi)
    lines=['リアルタイムランキング', f'{y}年{mo}月{d}日({WD[dt.weekday()]}) {h:02d}:{mi:02d}更新']
    lead=int(SIZE*1.2*SS)  # 自動行送り120%
    W=int(SIZE*16*SS); H=lead*2+int(SIZE*SS)
    pad=int(4*SS)
    txt=Image.new('L',(W+2*pad,H+2*pad),0); d_=ImageDraw.Draw(txt)
    for i,t in enumerate(lines): d_.text((pad,pad+i*lead),t,font=f,fill=255)
    bb=txt.getbbox()
    stk=txt.filter(ImageFilter.MaxFilter(2*int(1.5*SS)+1))
    glow=stk.filter(ImageFilter.GaussianBlur(2*SS))
    lay=Image.new('RGBA',txt.size,(255,255,255,0))
    lay=Image.composite(Image.new('RGBA',txt.size,(255,255,255,255)),lay,glow.point(lambda v:min(255,v*2)))
    lay=Image.composite(Image.new('RGBA',txt.size,(255,255,255,255)),lay,stk)
    lay=Image.composite(Image.new('RGBA',txt.size,(0,0,0,255)),lay,txt)
    lay=lay.resize((lay.width//SS,lay.height//SS),Image.LANCZOS)
    # 元の左上 (文字の見た目の左上) に合わせ、上に DY px
    ox,oy=l.bbox[0],l.bbox[1]-DY
    base.alpha_composite(lay,(ox-bb[0]//SS, oy-bb[1]//SS))
base.convert('RGB').save(outp)
base.convert('RGB').crop((40,470,1100,890)).resize((2120,840)).save(outp.replace('.png','_crop.png'))
