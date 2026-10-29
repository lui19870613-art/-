import sys, re, datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

src, out, fontdir = sys.argv[1], sys.argv[2], sys.argv[3]
BOLD = fontdir + '/NotoSansCJK-Bold.ttc'
REG = fontdir + '/NotoSansCJK-Regular.ttc'
WD = '月火水木金土日'
SS = 4  # supersampling
MAXW = 121

def add(img, name, top, left, after):
    nl = PixelLayer.frompil(img, psd, 'date', top, left)
    nl.name = name
    grp.insert(grp.index(after) + 1, nl)


psd = PSDImage.open(src)
ab = [l for l in psd if l.name == 'アートボード 2'][0]
grp = [l for l in ab if l.is_group()][0]
layers = list(grp)

def fmt(dt):
    return f"{dt.year}年{dt.month}月{dt.day}日({WD[dt.weekday()]}) {dt:%H:%M}更新"

def render(lines, sizes, color, stroke, glow, align='left', width=None, gap=1.0, font=BOLD):
    """Render text lines at SS scale with white stroke + soft white glow; returns RGBA at 1x."""
    fonts = [ImageFont.truetype(font, int(s * SS), index=0) for s in sizes]
    pad = int((stroke + glow * 2 + 2) * SS)
    boxes = [f.getbbox(t, stroke_width=0) for t, f in zip(lines, fonts)]
    ws = [b[2] for b in boxes]
    W = (width * SS if width else max(ws)) + pad * 2
    lh = [int(s * SS * 1.18) for s in sizes]
    H = sum(lh) + int(gap * SS) * (len(lines) - 1) + pad * 2
    txt = Image.new('L', (W, H), 0); stk = Image.new('L', (W, H), 0)
    dt, ds = ImageDraw.Draw(txt), ImageDraw.Draw(stk)
    y = pad
    for t, f, w, h in zip(lines, fonts, ws, lh):
        x = pad if align == 'left' else W - pad - w
        ds.text((x, y), t, font=f, fill=255, stroke_width=int(stroke * SS), stroke_fill=255)
        dt.text((x, y), t, font=f, fill=255)
        y += h + int(gap * SS)
    glow_a = stk.filter(ImageFilter.GaussianBlur(glow * SS)).point(lambda v: min(255, int(v * 1.6)))
    img = Image.new('RGBA', (W, H), (255, 255, 255, 0))
    white = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    img = Image.composite(white, img, glow_a)               # 光彩（外側）
    img = Image.composite(white, img, stk)                  # 境界線（白フチ）
    img = Image.composite(Image.new('RGBA', (W, H), color + (255,)), img, txt)
    img = img.resize((W // SS, H // SS), Image.LANCZOS)
    return img, pad // SS

pat = re.compile(r'^(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2})(?::\d{2})?更新$')
import numpy as np
W0, H0 = psd.size
def alpha_of(l):
    a = np.zeros((H0, W0), bool)
    im = l.composite()
    if im is None: return a
    m = np.array(im.convert('RGBA'))[..., 3] > 0
    x0, y0 = l.left, l.top
    a[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
    return a
banners = [l for l in layers if l.kind == 'pixel' and l.name.startswith('レイヤー 22') and l.visible]
masks = {id(b): alpha_of(b) for b in banners}

jobs = []
for i, l in enumerate(layers):
    if l.kind != 'type':
        continue
    m = pat.match(l.text.strip())
    if m:
        jobs.append((i, l, datetime.datetime(*map(int, m.groups()))))
dates, n = [], 0
plan = []
for i, l, dt in jobs:
    banner = layers[i - 1]  # 直下の帯
    assert banner.kind == 'pixel' and banner.name.startswith('レイヤー 22'), banner.name
    bx, by = banner.left, banner.top
    # 上に重なる帯で隠れる範囲
    occ = np.zeros((H0, W0), bool)
    for b in banners[banners.index(banner) + 1:]:
        occ |= masks[id(b)]
    x0, x1 = bx + 212, bx + 334          # ショップ名の右〜トロフィーの左
    ybot = by + 87                        # 帯の内側の下端
    # 上端：この範囲で隠れていない最初の行
    ytop = by + 40
    while occ[ytop, x0:x0 + 40].any(): ytop += 1
    ytop += 1
    # 右端：帯の下段で最初に隠れる列
    cols = occ[ytop:ybot, x0:x1].any(axis=0)
    xr = x0 + (int(np.argmax(cols)) if cols.any() else x1 - x0) - 3
    availw, availh = xr - x0, ybot - ytop
    plan.append((i, l, dt, x0, ytop, availw, availh))

lines0 = ['リアルタイムランキング', '2024年12月30日(土) 13:35更新']  # 最長パターンで基準を決める
sz = [10.5, 9.2]
def make(lines, k, h):
    img, pad = render(lines, [v * k for v in sz], (0, 0, 0), stroke=1.1, glow=1.4, gap=0.5)
    img = img.resize((round(img.width * h), img.height), Image.LANCZOS)
    return img, (round(pad * h), pad)
img, pad = make(lines0, 1, 1)
tw, th = img.width - 2 * pad[0], img.height - 2 * pad[1]
H = 0.85  # 長体85%
K = min(min((aw - 2) / (tw * H), (ah - 1) / th) for *_, aw, ah in plan)
K = min(K, 1.0)
print('uniform scale %.3f -> line1 %.1fpx line2 %.1fpx, hscale %.2f' % (K, sz[0]*K, sz[1]*K, H))
for i, l, dt, x0, ytop, availw, availh in plan:
    lines = ['リアルタイムランキング', fmt(dt)]
    img, pad = make(lines, K, H)
    tw, th = img.width - 2 * pad[0], img.height - 2 * pad[1]
    left = x0 - pad[0]
    top = ytop + (min(availh, 27) - th) // 2 - pad[1]
    add(img, f'日付 {dt:%Y/%m/%d %H:%M}', top, left, l)
    l.visible = False
    dates.append(dt); n += 1
    print(lines[1], 'avail', availw, availh, 'size', tw, th, 'ok' if tw <= availw and th <= availh else 'OVER')

# 集計期間
s = min(dates); e = max(dates)
for l in list(grp):
    if l.kind == 'type' and l.text.startswith('集計期間'):
        t = f"集計期間：{s.year}年{s.month}月{s.day}日～{e.year}年{e.month}月{e.day}日"
        img, pad = render([t], [15.0], (230, 230, 230), stroke=0, glow=0, font=REG)
        right = l.right
        add(img, t, l.top - pad - 4, right - (img.width - pad), l)
        l.visible = False
        print(t)
print('edited', n)
psd.save(out)
