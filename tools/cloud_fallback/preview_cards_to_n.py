import sys, re, datetime
from PIL import Image
from psd_tools import PSDImage
psd = PSDImage.open(sys.argv[1]); out = sys.argv[2]
L = list(psd)
cards = [l for l in L if l.kind == 'pixel' and l.visible and 150 <= l.width <= 1120 and l.height < 150]
RE = re.compile(r'(\d{4})\s*[/年.\-]\s*(\d{1,2})\s*[/月.\-]\s*(\d{1,2})')
dates = [l for l in L if l.kind == 'type' and '集計期間' not in l.text and RE.search(l.text)]
# 列：left+top がほぼ一定
def col(l): return round((l.left + l.top) / 280)
cols = {}
for c in cards: cols.setdefault(col(c), []).append(c)
print({k: len(v) for k, v in cols.items()})
# 日付→カード（日付を完全に含むカードのうち最前面）
def card_of(d):
    cs = [c for c in cards if c.left <= d.left and c.top <= d.top and c.right >= d.right and c.bottom >= d.bottom]
    return max(cs, key=L.index) if cs else None
pairs = []
for d in dates:
    y, m, dd = map(int, RE.search(d.text).groups()); c = card_of(d)
    pairs.append((datetime.date(y, m, dd), d, c))
colmax = {}
for dt, d, c in pairs:
    k = col(c); colmax[k] = max(colmax.get(k, dt), dt)
drop = sorted(colmax, key=lambda k: colmax[k])[0]
print('削除する列', drop, '最新', colmax[drop], '件数', len(cols[drop]))
keep_cards = [c for c in cards if col(c) != drop]
keep_dates = [d for dt, d, c in pairs if col(c) != drop]
dropped = set(id(x) for x in cols[drop]) | set(id(d) for dt, d, c in pairs if col(c) == drop)
items = keep_cards + keep_dates
ux0 = min(i.left for i in keep_cards); uy0 = min(i.top for i in keep_cards)
ux1 = max(i.right for i in keep_cards); uy1 = max(i.bottom for i in keep_cards)
fx0 = min(c.left for c in cards); fx1 = max(c.right for c in cards)
txt = {l.text[:4]: l for l in L if l.kind == 'type'}
top_lim = [l for l in L if l.kind=='type' and l.text.startswith('たくさん')][0].bottom + 6
bot_lim = [l for l in L if l.kind=='type' and l.text.startswith('在庫')][0].top - 6
s = min((fx1 - fx0) / (ux1 - ux0), (bot_lim - top_lim) / (uy1 - uy0))
nw, nh = (ux1 - ux0) * s, (uy1 - uy0) * s
nx0 = (fx0 + fx1) / 2 - nw / 2; ny0 = top_lim + ((bot_lim - top_lim) - nh) / 2
print(f'union ({ux0},{uy0})-({ux1},{uy1}) scale {s:.4f} -> ({nx0:.0f},{ny0:.0f})-({nx0+nw:.0f},{ny0+nh:.0f})')
skip = set(id(x) for x in items) | dropped
per = [l for l in L if 'た期間' in l.text] if False else None
base = psd.composite(layer_filter=lambda l: l.is_visible() and id(l) not in skip and l.layer_id not in {x.layer_id for x in items} and l.layer_id not in {x.layer_id for x in cols[drop]} and l.layer_id not in {d.layer_id for dt,d,c in pairs if col(c)==drop}).convert('RGBA')
for l in L:
    if l.layer_id not in {x.layer_id for x in items}: continue
    im = l.composite()
    if im is None: continue
    w, h = round(im.width * s), round(im.height * s)
    im = im.convert('RGBA').resize((w, h), Image.LANCZOS)
    x = round(nx0 + (l.left - ux0) * s); y = round(ny0 + (l.top - uy0) * s)
    base.alpha_composite(im, (x, y)) if x >= 0 and y >= 0 else base.paste(im, (x, y), im)
base.convert('RGB').save(out)
base.convert('RGB').crop((40, 460, 1110, 870)).resize((2140, 820)).save(out.replace('.png', '_crop.png'))
print('期間', min(dt for dt, d, c in pairs if col(c) != drop), max(dt for dt, d, c in pairs if col(c) != drop))
