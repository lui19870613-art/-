"""Photoshop がない環境用：日付を画像レイヤーとして描き込んだ PSD / JPEG を作る（マニュアル第2〜6章に準拠）。

使い方:
  python3 -I raster_dates.py <元.psd> <出力.psd> <出力.jpg> <フォントdir> [アートボード/グループ名]

- 元の日付文字レイヤーは削除せず非表示にし、その上（最前面）に画像レイヤーを追加する。
- 文字は全件同じサイズ。各カードの「手前のカードに隠れない範囲」に収まる最大サイズを使う。
- 「セレクトショップKK」はカード画像に焼き込まれているため、カード左端+SHOP_FREE_X より右に置く。
"""
import sys, re, datetime
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

src, out_psd, out_jpg, fontdir = sys.argv[1:5]
args = sys.argv[5:]
# --oneline-original : 第9章の例外。日付だけを1行にして、元の日付の位置（ショップ名の下）に置く
ONE = '--oneline-original' in args
args = [a for a in args if not a.startswith('--')]
target = args[0] if args else None
BOLD = fontdir + '/NotoSansCJK-Bold.ttc'
REG = fontdir + '/NotoSansCJK-Regular.ttc'
WD = '月火水木金土日'
SS = 4                 # 描画の拡大率（なめらかにするため）
SIZE0 = None           # None = 日付の数から自動（第3-1節）
STROKE, GLOW_CHOKE, GLOW_SIZE = 2, 1, 2   # 第3-2節
if '--oneline-original' in sys.argv:       # 小さい文字では2pxのフチがにじむので細くする（第3-2節の注意）
    STROKE, GLOW_CHOKE, GLOW_SIZE = 1, 0, 1
MARGIN, SHOP_FREE_X = 5, 213
RE = re.compile(r'(\d{4})\s*[/年.\-]\s*(\d{1,2})\s*[/月.\-]\s*(\d{1,2})\s*日?\s*(?:[(（][^)）]*[)）])?\s*(?:(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*\d{2})?)?')

psd = PSDImage.open(src)
grp = psd
if target:
    grp = [l for l in psd.descendants() if l.name == target and l.is_group()][0]
layers = list(grp)
W0, H0 = psd.size


def lines_for(y, mo, d, h, mi):
    dt = datetime.date(y, mo, d)
    if h is None:
        p = dt - datetime.timedelta(days=1)
        return ['デイリーランキング', f'{y}年{mo}月{d}日({WD[dt.weekday()]})更新 (集計日：{p.month}月{p.day}日)']
    return ['リアルタイムランキング', f'{y}年{mo}月{d}日({WD[dt.weekday()]}) {h:02d}:{mi:02d}更新']


def render(lines, size):
    if ONE:
        lines = [lines[1]]
    """黒文字＋白フチ（外側）＋白い光彩。戻り値：(画像, 文字の左上オフセット, 文字幅, 文字高さ)"""
    f = ImageFont.truetype(BOLD, round(size * SS), index=0)
    lead = round(size * 1.2 * SS)                    # 自動行送り
    pad = (STROKE + GLOW_SIZE + 2) * SS
    W = max(f.getbbox(t)[2] for t in lines) + pad * 2
    H = lead * (len(lines) - 1) + round(size * 1.4 * SS) + pad * 2
    txt = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(txt)
    for i, t in enumerate(lines):
        d.text((pad, pad + i * lead), t, font=f, fill=255)
    bb = txt.getbbox()
    stk = txt.filter(ImageFilter.MaxFilter(2 * STROKE * SS + 1))
    glow = stk.filter(ImageFilter.MaxFilter(2 * GLOW_CHOKE * SS + 1)).filter(ImageFilter.GaussianBlur(GLOW_SIZE * SS / 2))
    img = Image.new('RGBA', (W, H), (255, 255, 255, 0))
    whiteim = Image.new('RGBA', (W, H), (255, 255, 255, 255))
    img = Image.composite(whiteim, img, glow)
    img = Image.composite(whiteim, img, stk)
    img = Image.composite(Image.new('RGBA', (W, H), (0, 0, 0, 255)), img, txt)
    img = img.resize((W // SS, H // SS), Image.LANCZOS)
    return img, (bb[0] // SS, bb[1] // SS), (bb[2] - bb[0]) / SS, (bb[3] - bb[1]) / SS


def mask(l):
    a = np.zeros((H0, W0), bool)
    im = l.composite()
    if im is not None:
        m = np.array(im.convert('RGBA'))[..., 3] > 0
        y0, x0 = max(l.top, 0), max(l.left, 0)
        m = m[y0 - l.top:, x0 - l.left:][:H0 - y0, :W0 - x0]
        a[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
    return a


# カード（第4-2節）と日付（第2章）
cards = [l for l in layers if l.kind == 'pixel' and l.visible and 150 <= l.width <= 1120 and l.height < 300]
masks = {l.layer_id: mask(l) for l in cards}
dates, period = [], None
for l in layers:
    if l.kind != 'type':
        continue
    if '集計期間' in l.text:
        period = l
        continue
    m = RE.search(l.text)
    if m:
        y, mo, d = map(int, m.groups()[:3])
        h, mi = (int(m.group(4)), int(m.group(5))) if m.group(4) else (None, None)
        dates.append(dict(layer=l, y=y, mo=mo, d=d, h=h, mi=mi, lines=lines_for(y, mo, d, h, mi)))
print(f'日付 {len(dates)} 件 / カード {len(cards)} 枚')

# 各日付のカードと、手前のカードに隠れない範囲
for D in dates:
    l = D['layer']
    def ov(c):
        return max(0, min(l.right, c.right) - max(l.left, c.left)) * max(0, min(l.bottom, c.bottom) - max(l.top, c.top))
    # 日付のすぐ下のレイヤーが重なるカードなら、それが所属カード。なければ見えている面積が最大のカード
    i = layers.index(l)
    below = next((x for x in reversed(layers[:i]) if x.kind == 'pixel' and x.visible), None)
    if below in cards and ov(below) > 0:
        c = below
    else:
        def vis(c):
            occ_c = np.zeros((H0, W0), bool)
            for o in cards:
                if layers.index(o) > layers.index(c):
                    occ_c |= masks[o.layer_id]
            return (masks[c.layer_id] & ~occ_c)[l.top:l.bottom, l.left:l.right].sum()
        c = max(cards, key=vis)
    if ov(c) == 0:
        D['card'] = None
        print('！対応するカードなし：', l.text)
        continue
    idx = layers.index(c)
    occ = np.zeros((H0, W0), bool)
    for o in cards:
        if layers.index(o) > idx:          # psd-tools は下から順なので、後ろのものほど手前
            occ |= masks[o.layer_id]
    x0 = max(l.left, c.left + (SHOP_FREE_X if 380 <= c.width <= 440 else 0), c.left + MARGIN)
    yb = c.bottom - MARGIN
    yt = c.top + MARGIN
    while yt < yb and occ[yt, x0:x0 + 40].any():
        yt += 1
    yt += 1
    cols = occ[yt:yb, x0:c.right - MARGIN].any(axis=0)
    xr = x0 + (int(np.argmax(cols)) if cols.any() else c.right - MARGIN - x0) - 3
    if ONE:
        x0, yt, yb = l.left, l.top - 3, c.bottom - 2   # 元の行（ショップ名の下〜帯の下端）
        cols = occ[yt:yb, x0:c.right - MARGIN].any(axis=0)
        xr = x0 + (int(np.argmax(cols)) if cols.any() else c.right - MARGIN - x0) - 2
    D.update(card=c, box=(x0, yt, xr, yb))

# 文字サイズ：目安（第3-1節）から 0.5 ずつ下げ、全件が収まる最大サイズ
n = len(dates)
size = SIZE0 or (13 if n <= 4 else 12 if n <= 11 else 10 if n <= 30 else 9)
s = size
def fits(s):
    for D in dates:
        if D['card'] is None:
            continue
        _, _, tw, th = render(D['lines'], s)
        x0, yt, xr, yb = D['box']
        if tw > xr - x0 or th > yb - yt:
            return False
    return True
while s > 5 and not fits(s):
    s -= 0.25 if ONE else 0.5
print(f'文字サイズ：目安 {size} → {s}')

for D in dates:
    l = D['layer']
    l.visible = False                       # 元の文字は削除せず非表示
    if D['card'] is None:
        continue
    img, (ox, oy), tw, th = render(D['lines'], s)
    x0, yt, xr, yb = D['box']
    L = max(x0, min(l.left, xr - tw))
    T = max(yt, min(l.top - (0 if ONE else 8), yb - th))     # 元の左上から8px上（第2-3節）→ 範囲内へ（1行モードは元の位置）
    nl = PixelLayer.frompil(img, psd, 'date', round(T) - oy, round(L) - ox)
    nl.name = D['lines'][1] if ONE else ' '.join(D['lines'])
    grp.append(nl)                          # 最前面（第2-3節）
    print(' ', l.text, '→', ' / '.join(D['lines']))

# 集計期間（第6章）
if period is not None and dates:
    key = lambda D: (D['y'], D['mo'], D['d'])
    a, b = min(dates, key=key), max(dates, key=key)
    t = f"集計期間：{a['y']}年{a['mo']}月{a['d']}日～{b['y']}年{b['mo']}月{b['d']}日"
    if t == period.text:
        print('集計期間：変更なし')
    else:
        sz = period.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['FontSize'] * period.transform[3]
        f = ImageFont.truetype(REG, round(sz * SS), index=0)
        bb = f.getbbox(t)
        im = Image.new('RGBA', (bb[2] + 8 * SS, round(sz * 1.6 * SS)), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((4 * SS, 0), t, font=f, fill=(230, 230, 230, 255))
        im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
        ib = im.getbbox()
        nl = PixelLayer.frompil(im, psd, 'period', period.top - ib[1], period.right - ib[2])
        nl.name = t
        grp.append(nl)
        period.visible = False
        print('集計期間：→', t)

psd.save(out_psd)
psd2 = PSDImage.open(out_psd)
psd2.composite(force=True).convert('RGB').save(out_jpg, quality=95, subsampling=0)
print('保存：', out_psd, out_jpg)
