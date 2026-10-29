"""Photoshop がない環境用：「○冠獲得」の数字とメダルの数・並べ方を変える（マニュアル第10章）。
あとで Photoshop で手を加えられる PSD を作る（文字は文字のまま、効果も元のまま）。
usbportcover_typec_ranking_new002 用に作成（30冠・10個×3段 → 20冠・6・7・7個の3段）。

使い方:
  python3 -I medals_to_n.py <元.psd> <出力.psd> <出力.jpg> [新しい数字=20] [各段の個数 例 6,7,7]

- 数字：「30」の文字レイヤーの文字を「20」に書き換える（小塚ゴシック Heavy・白・黒い影のまま。Photoshopで打ち直せる）。
  レイヤーの絵は、元の「0」と、元の「3」と同じ幅に縮めた「2」（InterDisplay-Black）で作る。
  Photoshop で文字を編集すると、本来の小塚ゴシックで描き直される。
- メダル：残す個数になるよう下の段から減らし、残したメダルの全レイヤー（土台・星・文字）を同じ倍率で拡大して並べ直す。
  メダル1個分ずつ「メダル 01」〜のグループにまとめる（グループごと動かす・拡大すれば文字が隠れない）。
- JPEG と埋め込みプレビューは、元ファイルに入っている Photoshop の描画をもとに、変えた部分だけ描き直して作る
  （psd-tools はドロップシャドウを描かないため）。
"""
import sys, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from psd_tools import PSDImage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from editable import replace_layer, move_scale, set_text, save_with_preview

src, out_psd, out_jpg = sys.argv[1:4]
NEW = sys.argv[4] if len(sys.argv) > 4 else '20'
ROWS = [int(x) for x in (sys.argv[5] if len(sys.argv) > 5 else '').split(',') if x] or None
FONT = '/usr/share/fonts/opentype/inter/InterDisplay-Black.otf'

psd = PSDImage.open(src)
L = list(psd)
flat = psd.composite().convert('RGB')                 # 元ファイルの埋め込み画像（Photoshop が描いたもの・影あり）
W0, H0 = psd.size


def shadow_params(layer):
    for e in (layer.effects if layer.has_effects() else []):
        if type(e).__name__ == 'DropShadow' and e.enabled:
            ang = math.radians(e.angle)
            col = tuple(round(e.color.get(k, 0)) for k in (b'Rd  ', b'Grn ', b'Bl  '))
            return round(-math.cos(ang) * e.distance), round(math.sin(ang) * e.distance), col, e.opacity
    return None


def with_shadow(im, sp):
    """RGBA 画像に、ぼかしなしのドロップシャドウを付けた画像と、その左上のずれを返す。"""
    if not sp:
        return im, (0, 0)
    dx, dy, col, op = sp
    pad = max(abs(dx), abs(dy)) + 1
    out = Image.new('RGBA', (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new('RGBA', im.size, col + (0,)); sh.putalpha(im.getchannel('A').point(lambda v: round(v * op / 100)))
    out.alpha_composite(sh, (pad + dx, pad + dy)); out.alpha_composite(im, (pad, pad))
    return out, (-pad, -pad)


# ================= 数字（30 → 20） =================
num = next(l for l in L if l.kind == 'type' and l.text.strip().isdigit())
a = np.array(num.topil().convert('RGBA'))[..., 3]
lab, k = ndimage.label(a > 0)                         # 字間が詰まっているので、つながった塊で1文字ずつに分ける
assert k == 2, f'数字が2つの塊に分かれない（{k}）'
first, second = sorted(range(1, k + 1), key=lambda i: np.where(lab == i)[1].min())
ys, xs = np.where(lab == first)
gh = ys.max() - ys.min() + 1
assert len(NEW) == 2 and NEW[1] == num.text.strip()[1], '2文字目が同じ数字のときだけ対応'


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


g = glyph(NEW[0], gh)
g = np.array(g.resize((xs.max() - xs.min() + 1, g.height), Image.LANCZOS))   # 元の1文字目と同じ幅にそろえる
canvas = np.zeros(a.shape, np.uint8)
canvas[lab == second] = a[lab == second]              # 「0」はそのまま
y0 = ys.min(); h = min(g.shape[0], canvas.shape[0] - y0)
x0 = xs.min()
canvas[y0:y0 + h, x0:x0 + g.shape[1]] = np.maximum(canvas[y0:y0 + h, x0:x0 + g.shape[1]], g[:h])
glyph_img = Image.new('RGBA', (canvas.shape[1], canvas.shape[0]), (255, 255, 255, 0)); glyph_img.putalpha(Image.fromarray(canvas))
num_sp = shadow_params(num)
num_box = (num.left, num.top, num.right, num.bottom)
num_left, num_top = num.left, num.top
print('数字：', num.text, '→', NEW)

# ================= メダル =================
band = next(l for l in L if l.kind == 'pixel' and l.visible and l.width > 1000 and 600 < l.top < 800)   # 白い帯
parts = [l for l in L if l.visible and l.top >= band.top and l.width < 200 and l.top < H0]
bases_all = [l for l in parts if l.kind == 'pixel' and l.name.startswith('レイヤー 25')]
row_tops = sorted({round(b.top / 50) * 50 for b in bases_all})


def row(l):
    return min(range(len(row_tops)), key=lambda i: abs(l.top - row_tops[i]) if l.top >= row_tops[i] - 30 else 1e9)


target = int(NEW)
counts = {}
for b in bases_all:
    counts[row(b)] = counts.get(row(b), 0) + 1
keep_rows, total = [], 0
for i in sorted(counts):
    if total + counts[i] <= target:
        keep_rows.append(i); total += counts[i]
assert total == target, f'段ごとに消すと {total} 個になる'
keep = [l for l in parts if row(l) in keep_rows]
drop = [l for l in parts if row(l) not in keep_rows]
bases = [b for b in bases_all if row(b) in keep_rows]
groups = {b.layer_id: [] for b in bases}
for l in keep:                                        # 中心がいちばん近い土台に割り当てる
    cx, cy = (l.left + l.right) / 2, (l.top + l.bottom) / 2
    b = min(bases, key=lambda b: ((b.left + b.right) / 2 - cx) ** 2 + ((b.top + b.bottom) / 2 - cy) ** 2)
    assert b.left - 15 <= cx <= b.right + 15 and b.top - 15 <= cy <= b.bottom + 15, f'メダルに入らないレイヤー：{l.name}'
    groups[b.layer_id].append(l)
order = sorted(bases, key=lambda b: (row(b), b.left))

# 確認用：メダル1個分を影ごと画像にする（並べ方の計算と JPEG 用）
medals = []
for b in order:
    im = Image.new('RGBA', psd.size, (0, 0, 0, 0))
    for l in sorted(groups[b.layer_id], key=L.index):
        li = l.composite()
        if li is None:
            continue
        li, (ox, oy) = with_shadow(li.convert('RGBA'), shadow_params(l))
        im.alpha_composite(li, (l.left + ox, l.top + oy))
    bb = im.getbbox()
    medals.append((im.crop(bb), bb[0], bb[1]))
uw = max(m.width for m, _, _ in medals); uh = max(m.height for m, _, _ in medals)
ROWS = ROWS or [counts[i] for i in keep_rows]
assert sum(ROWS) == len(medals), f'並べ方の合計 {sum(ROWS)} とメダル数 {len(medals)} が違う'

area_top, area_bot = band.top, H0
SIDE, MIN_GAP = 15, 8
nmax, nrow = max(ROWS), len(ROWS)
sc = min((W0 - SIDE * 2) / (nmax * uw), (area_bot - area_top - MIN_GAP * (nrow + 1)) / (nrow * uh))
cw, ch = uw * sc, uh * sc
gx = (W0 - SIDE * 2 - nmax * cw) / max(1, nmax - 1)
gy = (area_bot - area_top - nrow * ch) / (nrow + 1)
print(f'並べ方 {ROWS}・拡大 {sc * 100:.1f}%（メダル {round(cw)}×{round(ch)}px）')
places = []
k = 0
for r, n in enumerate(ROWS):
    x_start = (W0 - (n * cw + (n - 1) * gx)) / 2
    y = area_top + gy + r * (ch + gy)
    for j in range(n):
        m, bx, by = medals[k]
        mw, mh = m.width * sc, m.height * sc
        cx = x_start + j * (cw + gx) + cw / 2; cy = y + ch / 2
        places.append((round(cx - mw / 2), round(cy - mh / 2)))   # 影込みの左上
        k += 1

# ================= 確認用の画像（JPEG・埋め込みプレビュー） =================
preview = flat.copy()
bg = psd.composite(layer_filter=lambda l: l.layer_id in {L[0].layer_id, L[1].layer_id} and l.is_visible()).convert('RGB')   # 赤い背景だけ
nb = (num_box[0] - 15, num_box[1] - 15, num_box[2] + 15, num_box[3] + 15)
preview.paste(bg.crop(nb), nb[:2])                    # 「30」を消す
gi, (ox, oy) = with_shadow(glyph_img, num_sp)
preview.paste(gi, (num_left + ox, num_top + oy), gi)
band_img = band.composite().convert('RGBA')
preview.paste(Image.new('RGB', (W0, H0 - band.top), (255, 255, 255)), (0, band.top))
preview.paste(band_img, (band.left, band.top), band_img)   # 白い帯（メダルなし）
for (m, _, _), (px_, py_) in zip(medals, places):
    m2 = m.resize((round(m.width * sc), round(m.height * sc)), Image.LANCZOS)
    preview.paste(m2, (px_, py_), m2)

# ================= 編集できる PSD =================
nl = replace_layer(psd, num, glyph_img, num_left, num_top)
set_text(nl, NEW)
for l in drop:
    psd.remove(l)
for idx, (b, (m, bx, by), (px_, py_)) in enumerate(zip(order, medals, places)):
    new_layers = [move_scale(psd, l, sc, bx, by, px_, py_) for l in sorted(groups[b.layer_id], key=L.index)]
    grp = psd.create_group(new_layers, name=f'medal {idx + 1:02d}')
    grp.name = f'メダル {idx + 1:02d}'
save_with_preview(psd, out_psd, preview)
preview.save(out_jpg, quality=95, subsampling=0)
print('保存', out_psd, out_jpg)
