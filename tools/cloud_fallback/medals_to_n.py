"""Photoshop がない環境用：「○冠獲得」の数字とメダルの数を変える（マニュアル第10章）。
usbportcover_typec_ranking_new002 用に作成（30冠・10個×3段 → 20冠・10個×2段）。

使い方:
  python3 -I medals_to_n.py <元.psd> <出力.psd> <出力.jpg> [新しい数字=20]

- 数字：元の「30」の画像から「0」をそのまま使い、「2」だけ InterDisplay-Black で描く（白・黒い影 11px/127°）。
  元の文字レイヤーは非表示で残す。
- メダル：いちばん下の段を削除し、残った段を白い帯の中で上下中央へ移動する。
  文字レイヤーは画像化せず、位置（レイヤー位置＋文字の変形情報）だけ動かすので、Photoshop で編集できるまま。
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
y0 = min(l.top for l in keep); y1 = max(l.bottom for l in keep)
area_top, area_bot = band.top, psd.height
shift = round((area_top + area_bot) / 2 - (y0 + y1) / 2)
print(f'メダル {total} 個を残し、{len(drop)} レイヤーを削除。{shift}px 下へ移動')

for l in drop:
    psd.remove(l)
for l in keep:
    if l.kind == 'type':                              # 文字の変形情報も同じだけ動かす（Photoshopで再描画しても同じ位置）
        ts = l.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
        t = list(ts.transform); t[5] += shift; ts.transform = tuple(t)
    l.offset = (l.left, l.top + shift)

psd.save(out_psd)
PSDImage.open(out_psd).composite(force=True).convert('RGB').save(out_jpg, quality=95, subsampling=0)
print('保存', out_psd, out_jpg)
