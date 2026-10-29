"""Photoshop がない環境用：帯（カード）を列ごと減らし、残りを拡大して並べ直す（tools/cards_to_n.jsx と同じ処理）。
あとで Photoshop で手を加えられる PSD を作る（日付・集計期間は文字のまま、効果も元のまま）。

使い方:
  python3 -I cards_to_n.py <元.psd> <出力.psd> <出力.jpg> <フォントdir> [残す枚数=20]

- 帯は画像のまま、日付は文字レイヤーのまま、同じ倍率で拡大して移動する（文字の変形情報も直すので、打ち直しても同じ位置）。
- 集計期間は文字レイヤーの文字を書き換える。レイヤーの絵は Noto Sans で仮に描く（Photoshop で編集すると小塚ゴシックで描き直される）。
- JPEG と埋め込みプレビューは、元ファイルに入っている Photoshop の描画をもとに、帯の部分と集計期間だけ描き直して作る。
"""
import sys, re, datetime, os
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from editable import move_scale, replace_layer, set_text, save_with_preview

src, out_psd, out_jpg, fontdir = sys.argv[1:5]
COUNT = int(sys.argv[5]) if len(sys.argv) > 5 else 20
REG = fontdir + '/NotoSansCJK-Regular.ttc'
SS = 4
RE = re.compile(r'(\d{4})\s*[/年.\-]\s*(\d{1,2})\s*[/月.\-]\s*(\d{1,2})')

psd = PSDImage.open(src)
L = list(psd)
flat = psd.composite().convert('RGB')                 # 元ファイルの埋め込み画像（Photoshop の描画）
W0, H0 = psd.size
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
top_text = next(l for l in L if l.kind == 'type' and l.text.startswith('たくさん'))
bot_text = next(l for l in L if l.kind == 'type' and l.text.startswith('在庫'))
top_lim, bot_lim = top_text.bottom + 6, bot_text.top - 6
s = min((fx1 - fx0) / (ux1 - ux0), (bot_lim - top_lim) / (uy1 - uy0))
nx0 = (fx0 + fx1) / 2 - (ux1 - ux0) * s / 2
ny0 = top_lim + ((bot_lim - top_lim) - (uy1 - uy0) * s) / 2
print(f'拡大 {s * 100:.1f}%')

# 集計期間（第6章）
mn, mx = min(dt for dt, _ in keep_dates), max(dt for dt, _ in keep_dates)
period_text = f'集計期間：{mn.year}年{mn.month}月{mn.day}日～{mx.year}年{mx.month}月{mx.day}日'
print(period_text)

# ================= 確認用の画像 =================
preview = flat.copy()
bg = psd.composite(layer_filter=lambda l: l.layer_id in {L[0].layer_id, L[1].layer_id} and l.is_visible()).convert('RGB')
region = (0, top_text.bottom + 1, W0, bot_text.top)   # 帯がある部分を赤い背景に戻す
preview.paste(bg.crop(region), region[:2])
layered = sorted(keep_cards + [d for _, d in keep_dates], key=L.index)   # 元の重なり順（下から）
for l in layered:
    im = l.composite()                                # 帯の画像・日付（白フチ込み）
    if im is None:
        continue
    im = im.convert('RGBA')
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    preview.paste(im, (round(nx0 + (l.left - ux0) * s), round(ny0 + (l.top - uy0) * s)), im)
period_img = None
if period is not None and period.text != period_text:
    sz = period.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['FontSize'] * period.transform[3]
    f = ImageFont.truetype(REG, round(sz * SS), index=0)
    im = Image.new('RGBA', (f.getbbox(period_text)[2] + 8 * SS, round(sz * 1.6 * SS)), (230, 230, 230, 0))
    ImageDraw.Draw(im).text((4 * SS, 0), period_text, font=f, fill=(230, 230, 230, 255))
    im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
    period_img = im.crop(im.getbbox())
    pr = (period.left - 2, period.top - 2, period.right + 2, period.bottom + 2)
    preview.paste(bg.crop(pr), pr[:2])
    p_left, p_top = period.right - period_img.width, period.top   # 右端をそろえる
    preview.paste(period_img, (p_left, p_top), period_img)

# ================= 編集できる PSD =================
for col in drop:
    for c in col['cards']:
        psd.remove(c)
    for _, d in col['dates']:
        psd.remove(d)
for l in layered:
    move_scale(psd, l, s, ux0, uy0, nx0, ny0)
if period_img is not None:
    nl = replace_layer(psd, period, period_img, p_left, p_top)
    set_text(nl, period_text)
    from psd_tools.constants import Tag
    ts = nl.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
    xx, xy, yx, yy, tx, ty = ts.transform
    ts.transform = (xx, xy, yx, yy, tx + (p_left - period.left), ty)   # 右端をそろえた分だけ文字の基準点も動かす
print(f'残した帯 {len(keep_cards)} 枚・日付 {len(keep_dates)} 件')
save_with_preview(psd, out_psd, preview)
preview.save(out_jpg, quality=95, subsampling=0)
print('保存', out_psd, out_jpg)
