"""Photoshop がない環境用：帯（カード）を列ごと減らし、残りを拡大して並べ直した PSD / JPEG を作る。
（tools/cards_to_n.jsx と同じ処理。日付と集計期間は画像として描き直す＝文字は編集できない・フォントは代用）

使い方:
  python3 -I cards_to_n.py <元.psd> <出力.psd> <出力.jpg> <フォントdir> [残す枚数=20]
"""
import sys, re, datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

src, out_psd, out_jpg, fontdir = sys.argv[1:5]
COUNT = int(sys.argv[5]) if len(sys.argv) > 5 else 20
BOLD = fontdir + '/NotoSansCJK-Bold.ttc'
REG = fontdir + '/NotoSansCJK-Regular.ttc'
SS = 4
RE = re.compile(r'(\d{4})\s*[/年.\-]\s*(\d{1,2})\s*[/月.\-]\s*(\d{1,2})')

psd = PSDImage.open(src)
L = list(psd)
cards = [l for l in L if l.kind == 'pixel' and l.visible and 150 <= l.width <= 1120 and l.height < 150]
dates = [l for l in L if l.kind == 'type' and '集計期間' not in l.text and RE.search(l.text)]
period = next((l for l in L if l.kind == 'type' and '集計期間' in l.text), None)

# 列分け（左端＋上端がほぼ一定）
cards.sort(key=lambda c: c.left + c.top)
cols, prev = [], None
for c in cards:
    k = c.left + c.top
    if prev is None or k - prev > 100:
        cols.append({'cards': [], 'dates': []})
    cols[-1]['cards'].append(c); prev = k
col_of = {c.layer_id: col for col in cols for c in col['cards']}
for d in dates:
    cs = [c for c in cards if c.left <= d.left and c.top <= d.top and c.right >= d.right and c.bottom >= d.bottom]
    c = max(cs, key=L.index)
    y, m, dd = map(int, RE.search(d.text).groups())
    col_of[c.layer_id]['dates'].append((datetime.date(y, m, dd), d))
for col in cols:
    col['newest'] = max(dt for dt, _ in col['dates'])
print('列:', [(len(c['cards']), len(c['dates']), str(c['newest'])) for c in cols])

remain, drop = len(cards), []
for col in sorted(cols, key=lambda c: c['newest']):
    if remain <= COUNT:
        break
    drop.append(col); remain -= len(col['cards'])
assert remain == COUNT, f'列ごとに消すと {remain} 枚になる'
keep = [c for c in cols if c not in drop]
keep_cards = [c for col in keep for c in col['cards']]
keep_dates = [(dt, d) for col in keep for dt, d in col['dates']]

fx0, fx1 = min(c.left for c in cards), max(c.right for c in cards)
ux0, uy0 = min(c.left for c in keep_cards), min(c.top for c in keep_cards)
ux1, uy1 = max(c.right for c in keep_cards), max(c.bottom for c in keep_cards)
top_lim = next(l for l in L if l.kind == 'type' and l.text.startswith('たくさん')).bottom + 6
bot_lim = next(l for l in L if l.kind == 'type' and l.text.startswith('在庫')).top - 6
s = min((fx1 - fx0) / (ux1 - ux0), (bot_lim - top_lim) / (uy1 - uy0))
nx0 = (fx0 + fx1) / 2 - (ux1 - ux0) * s / 2
ny0 = top_lim + ((bot_lim - top_lim) - (uy1 - uy0) * s) / 2
print(f'拡大 {s * 100:.1f}%')
pos = lambda x, y: (round(nx0 + (x - ux0) * s), round(ny0 + (y - uy0) * s))


def render_date(text, size, stroke=2):
    lines = text.replace('\n', '\r').split('\r')
    f = ImageFont.truetype(BOLD, round(size * SS), index=0)
    lead = round(size * 1.2 * SS); pad = (stroke + 2) * SS
    W = max(f.getbbox(t)[2] for t in lines) + pad * 2
    H = lead * (len(lines) - 1) + round(size * 1.4 * SS) + pad * 2
    txt = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(txt)
    for i, t in enumerate(lines):
        dr.text((pad, pad + i * lead), t, font=f, fill=255)
    bb = txt.getbbox()
    stk = txt.filter(ImageFilter.MaxFilter(2 * stroke * SS + 1))
    img = Image.new('RGBA', (W, H), (255, 255, 255, 0))
    img = Image.composite(Image.new('RGBA', (W, H), (255, 255, 255, 255)), img, stk)
    img = Image.composite(Image.new('RGBA', (W, H), (0, 0, 0, 255)), img, txt)
    return img.resize((W // SS, H // SS), Image.LANCZOS), (bb[0] // SS, bb[1] // SS)


# 新しいレイヤーを作ってから、元のレイヤーを消す（順番は元の位置に入れる）
replace = {}
for c in keep_cards:
    im = c.composite().convert('RGBA')
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = pos(c.left, c.top)
    nl = PixelLayer.frompil(im, psd, 'card', y, x); nl.name = c.name
    replace[c.layer_id] = nl
for dt, d in keep_dates:
    rs = d.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
    size = rs['FontSize'] * d.transform[3] * s
    im, (ox, oy) = render_date(d.text, size)
    x, y = pos(d.left, d.top)
    nl = PixelLayer.frompil(im, psd, 'date', y - oy, x - ox); nl.name = d.text.replace('\r', ' ')
    replace[d.layer_id] = nl
remove_ids = {c.layer_id for col in drop for c in col['cards']} | {d.layer_id for col in drop for _, d in col['dates']}
for l in list(psd):
    if l.layer_id in replace:
        psd.insert(psd.index(l), replace[l.layer_id]); psd.remove(l)
    elif l.layer_id in remove_ids:
        psd.remove(l)

# 集計期間（第6章）
mn, mx = min(dt for dt, _ in keep_dates), max(dt for dt, _ in keep_dates)
t = f'集計期間：{mn.year}年{mn.month}月{mn.day}日～{mx.year}年{mx.month}月{mx.day}日'
if period is not None and t != period.text:
    sz = period.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['FontSize'] * period.transform[3]
    f = ImageFont.truetype(REG, round(sz * SS), index=0)
    im = Image.new('RGBA', (f.getbbox(t)[2] + 8 * SS, round(sz * 1.6 * SS)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 * SS, 0), t, font=f, fill=(230, 230, 230, 255))
    im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
    ib = im.getbbox()
    nl = PixelLayer.frompil(im, psd, 'period', period.top - ib[1], period.right - ib[2]); nl.name = t
    psd.insert(psd.index(period) + 1, nl)
    period.visible = False
print(t)
print(f'残した帯 {len(keep_cards)} 枚・日付 {len(keep_dates)} 件')
psd.save(out_psd)
PSDImage.open(out_psd).composite(force=True).convert('RGB').save(out_jpg, quality=95, subsampling=0)
print('保存', out_psd, out_jpg)
