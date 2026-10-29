"""Photoshop がない環境用：「○冠獲得」の数字とメダルの数を変える（マニュアル第10章）。
usbportcover_typec_ranking_new002 用に作成（30冠・10個×3段 → 20冠・10個×2段）。

使い方:
  python3 -I medals_to_n.py <元.psd> <出力.psd> <出力.jpg> [新しい数字=20] [各段の個数 例 6,7,7]

- 数字：元の「30」の画像から「0」をそのまま使い、「2」だけ InterDisplay-Black で描く（白・黒い影 11px/127°）。
  元の文字レイヤーは非表示で残す。
- メダル：残す個数になるよう下の段から減らし、メダル1個分（土台・星・文字）を効果ごと1枚の画像にして、
  白い帯に収まる最大の大きさで並べ直す（各段は左右中央）。元のメダルのレイヤーは削除する。
  ※ psd-tools で既存レイヤーを動かすと Photoshop で崩れるおそれがあるため、既存レイヤーは動かさず新しいレイヤーで置く。
"""
import sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from psd_tools.constants import Tag

src, out_psd, out_jpg = sys.argv[1:4]
NEW = sys.argv[4] if len(sys.argv) > 4 else '20'
FONT = '/usr/share/fonts/opentype/inter/InterDisplay-Black.otf'

psd = PSDImage.open(src)
L = list(psd)

# ---- 数字（30 → 20） ----
num = next(l for l in L if l.kind == 'type' and l.text.strip().isdigit())
raw = np.array(num.topil().convert('RGBA'))           # 効果なしの文字だけ
a = raw[..., 3]
from scipy import ndimage
lab, k = ndimage.label(a > 0)                         # 字間が詰まっているので、つながった塊で1文字ずつに分ける
assert k == 2, f'数字が2つの塊に分かれない（{k}）'
comps = sorted(range(1, k + 1), key=lambda i: np.where(lab == i)[1].min())
first, second = comps
ys, xs = np.where(lab == first)
gh = ys.max() - ys.min() + 1
right1 = xs.max()                                     # 1文字目の右端（2文字目との間隔を保つ）
print('元の数字', num.text, '高さ', gh, '1文字目', xs.min(), '～', right1)

def glyph(ch, h):
    size = h * 1.4
    for _ in range(20):                               # 字の高さが h になるサイズを探す
        f = ImageFont.truetype(FONT, round(size))
        bb = f.getbbox(ch)
        if abs((bb[3] - bb[1]) - h) <= 1:
            break
        size = size * h / (bb[3] - bb[1])
    im = Image.new('L', (bb[2] + 10, bb[3] + 10), 0)
    ImageDraw.Draw(im).text((0, 0), ch, font=f, fill=255)
    return im.crop(im.getbbox())

assert len(NEW) == 2 and NEW[1] == num.text.strip()[1], '2文字目が同じ数字のときだけ対応'
g = glyph(NEW[0], gh)
g = np.array(g.resize((right1 - xs.min() + 1, g.height), Image.LANCZOS))   # 元の1文字目と同じ幅（長体）にそろえる
gx = xs.min()                                         # 元の1文字目と同じ位置
extra = max(0, -gx)
canvas = np.zeros((a.shape[0], a.shape[1] + extra), np.uint8)
second_mask = (lab == second)
canvas[:, extra:][second_mask] = a[second_mask]       # 「0」はそのまま
y0 = ys.min()
h = min(g.shape[0], canvas.shape[0] - y0)
canvas[y0:y0 + h, gx + extra:gx + extra + g.shape[1]] = np.maximum(canvas[y0:y0 + h, gx + extra:gx + extra + g.shape[1]], g[:h])
txt = Image.fromarray(canvas)
num_left = num.left - extra

# 影（元と同じ：距離11px・角度127°・ぼかし0・黒・乗算100%）
dist, ang = 11, math.radians(127)
dx, dy = round(-math.cos(ang) * dist), round(math.sin(ang) * dist)
pad = 20
W, H = txt.width + pad * 2, txt.height + pad * 2
shadow = Image.new('L', (W, H), 0); shadow.paste(txt, (pad + dx, pad + dy))
img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
img = Image.composite(Image.new('RGBA', (W, H), (4, 0, 0, 255)), img, shadow)
fill = Image.new('L', (W, H), 0); fill.paste(txt, (pad, pad))
img = Image.composite(Image.new('RGBA', (W, H), (255, 255, 255, 255)), img, fill)
nl = PixelLayer.frompil(img, psd, 'num', num.top - pad, num_left - pad)
nl.name = NEW
psd.insert(psd.index(num) + 1, nl)
num.visible = False
print('数字：', num.text, '→', NEW)

# ---- メダル（3段 → 2段） ----
band = next(l for l in L if l.kind == 'pixel' and l.visible and l.width > 1000 and 600 < l.top < 800)   # 白い帯
parts = [l for l in L if l.visible and l.top >= band.top and l.width < 200 and l.top < psd.height]
row_tops = sorted({round(l.top / 50) * 50 for l in parts if l.kind == 'pixel' and l.name.startswith('レイヤー 25')})
def row(l):
    return min(range(len(row_tops)), key=lambda i: abs(l.top - row_tops[i]) if l.top >= row_tops[i] - 30 else 1e9)
rows_ = {}
for l in parts:
    rows_.setdefault(row(l), []).append(l)
medal_rows = {i: sum(1 for l in v if l.kind == 'pixel' and l.name.startswith('レイヤー 25')) for i, v in rows_.items()}
print('段ごとのメダル数', medal_rows)
target = int(NEW)
keep_rows, total = [], 0
for i in sorted(rows_):
    if total + medal_rows[i] <= target:
        keep_rows.append(i); total += medal_rows[i]
assert total == target, f'段ごとに消すと {total} 個になる'
drop = [l for i in rows_ if i not in keep_rows for l in rows_[i]]
keep = [l for i in keep_rows for l in rows_[i]]
# 並べ方（各段の個数。例 "6,7,7"。指定がなければ元と同じ1段の個数で並べる）
ROWS = [int(x) for x in (sys.argv[5] if len(sys.argv) > 5 else '').split(',') if x] or None

# メダル1個分のレイヤーをまとめる（土台「レイヤー 25*」に、中心がいちばん近いレイヤーを割り当てる）
bases = [l for l in keep if l.kind == 'pixel' and l.name.startswith('レイヤー 25')]
groups = {b.layer_id: [] for b in bases}
for l in keep:
    cx, cy = (l.left + l.right) / 2, (l.top + l.bottom) / 2
    b = min(bases, key=lambda b: ((b.left + b.right) / 2 - cx) ** 2 + ((b.top + b.bottom) / 2 - cy) ** 2)
    assert b.left - 15 <= cx <= b.right + 15 and b.top - 15 <= cy <= b.bottom + 15, f'メダルに入らないレイヤー：{l.name}'
    groups[b.layer_id].append(l)
order = sorted(bases, key=lambda b: (row(b), b.left))   # 元の並び順（上の段の左から）

# 1個ずつ、効果ごと1枚の画像にする（文字も一緒に拡大されるので隠れない）
medals = []
for b in order:
    im = Image.new('RGBA', psd.size, (0, 0, 0, 0))
    for l in sorted(groups[b.layer_id], key=L.index):         # 下のレイヤーから順に重ねる
        if not l.is_visible():
            continue
        li = l.composite()
        if li is None:
            continue
        li = li.convert('RGBA')
        for e in (l.effects if l.has_effects() else []):
            # psd-tools はドロップシャドウを描かないので自分で描く（メダル土台と下の文字の「黒い部分」）
            if type(e).__name__ == 'DropShadow' and e.enabled:
                ang = math.radians(e.angle)
                dx, dy = round(-math.cos(ang) * e.distance), round(math.sin(ang) * e.distance)
                c = e.color
                col = tuple(round(c.get(k, 0)) for k in (b'Rd  ', b'Grn ', b'Bl  '))
                a = li.getchannel('A').point(lambda v, o=e.opacity: round(v * o / 100))
                sh = Image.new('RGBA', li.size, col + (0,)); sh.putalpha(a)
                im.alpha_composite(sh, (l.left + dx, l.top + dy))
        im.alpha_composite(li, (l.left, l.top))
    bb = im.getbbox()
    medals.append(im.crop(bb))
uw = max(m.width for m in medals); uh = max(m.height for m in medals)
ROWS = ROWS or [medal_rows[i] for i in keep_rows]
assert sum(ROWS) == len(medals), f'並べ方の合計 {sum(ROWS)} とメダル数 {len(medals)} が違う'

area_top, area_bot = band.top, psd.height
SIDE, MIN_GAP = 15, 8
nmax, nrow = max(ROWS), len(ROWS)
sc = min((psd.width - SIDE * 2) / (nmax * uw), (area_bot - area_top - MIN_GAP * (nrow + 1)) / (nrow * uh))
cw, ch = uw * sc, uh * sc
gx = (psd.width - SIDE * 2 - nmax * cw) / max(1, nmax - 1)     # 横のすき間（全段同じ）
gy = (area_bot - area_top - nrow * ch) / (nrow + 1)            # 縦のすき間（上下と段の間で同じ）
print(f'並べ方 {ROWS}・拡大 {sc * 100:.1f}%（メダル {round(cw)}×{round(ch)}px）')

for l in parts:                                               # 元のメダル（全段）を削除
    psd.remove(l)
k = 0
for r, n in enumerate(ROWS):
    roww = n * cw + (n - 1) * gx
    x0 = (psd.width - roww) / 2
    y = area_top + gy + r * (ch + gy)
    for j in range(n):
        m = medals[k]
        m2 = m.resize((round(m.width * sc), round(m.height * sc)), Image.LANCZOS)
        cx = x0 + j * (cw + gx) + cw / 2; cy = y + ch / 2      # 枠の中央に置く
        nl = PixelLayer.frompil(m2, psd, 'medal', round(cy - m2.height / 2), round(cx - m2.width / 2))
        k += 1
        nl.name = f'メダル {k:02d}'
        psd.append(nl)

psd.save(out_psd)
PSDImage.open(out_psd).composite(force=True).convert('RGB').save(out_jpg, quality=95, subsampling=0)
print('保存', out_psd, out_jpg)
