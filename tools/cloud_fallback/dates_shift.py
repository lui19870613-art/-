"""新しい日付を足して、古い日付を消し、帯の日付を古い順に並べ直す（帯の枚数はそのまま）。
あとで Photoshop で手を加えられる PSD を作る（日付・集計期間は文字レイヤーのまま、効果も元のまま）。

使い方:
  python3 -I dates_shift.py <元.psd> <出力.psd> <出力.jpg> <フォントdir> "2026/09/16 03:53" ["2026/09/16 03:53" ...]

- 並び順：左の列の下から上へ、続いて右の列の下から上へ、古い順。右上がいちばん新しい日付。
- 足した数だけ、いちばん古い日付を消す。
- 日付の文字は「リアルタイムランキング／YYYY年M月D日(曜) HH:MM更新」（時刻なしならデイリー表記・マニュアル第2章）。
- 文字レイヤーの位置・大きさ・効果はそのままで、中身の文字だけ書き換える。
  レイヤーの絵は、同じ日付がすでにあればその絵を使い、新しい日付は Noto Sans で仮に描く
  （Photoshop で文字を編集すると小塚ゴシックで描き直される）。
- 集計期間を、残った日付の最初～最後に書き換える（第6章）。
"""
import sys, re, datetime, os
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from editable import replace_layer, set_text, save_with_preview, repair, true_pixels

src, out_psd, out_jpg, fontdir = sys.argv[1:5]
NEW = sys.argv[5:]
BOLD = fontdir + '/NotoSansCJK-Bold.ttc'
REG = fontdir + '/NotoSansCJK-Regular.ttc'
SS = 4
WD = '月火水木金土日'
RE = re.compile(r'(\d{4})\s*[/年.\-]\s*(\d{1,2})\s*[/月.\-]\s*(\d{1,2})\s*日?\s*(?:[(（][^)）]*[)）])?\s*(?:(\d{1,2})\s*[:：]\s*(\d{2}))?')


def parse(t):
    m = RE.search(t)
    y, mo, d = map(int, m.groups()[:3])
    if m.group(4):
        return datetime.datetime(y, mo, d, int(m.group(4)), int(m.group(5))), True
    return datetime.datetime(y, mo, d), False


def fmt(dt, has_time):
    w = WD[dt.weekday()]
    if has_time:
        return f'リアルタイムランキング\r{dt.year}年{dt.month}月{dt.day}日({w}) {dt:%H:%M}更新'
    p = dt - datetime.timedelta(days=1)
    return f'デイリーランキング\r{dt.year}年{dt.month}月{dt.day}日({w})更新 (集計日：{p.month}月{p.day}日)'


psd = PSDImage.open(src)
flat = psd.composite().convert('RGB')                 # 元ファイルの Photoshop の描画
n_fix = repair(psd)                                   # 「黒い四角＋マスク」になったレイヤーを直す
if n_fix:
    print('透明を直したレイヤー：', n_fix)
    tmp0 = out_psd + '.fix.psd'
    psd.save(tmp0)                                    # 直したレイヤーを文字レイヤーとして読み直す
    psd = PSDImage.open(tmp0)
    os.remove(tmp0)
L = list(psd)
dates = [l for l in L if l.kind == 'type' and '集計期間' not in l.text and RE.search(l.text)]
period = next((l for l in L if l.kind == 'type' and '集計期間' in l.text), None)
cards = [l for l in L if l.kind == 'pixel' and l.visible and 150 <= l.width <= 1120 and l.height < 150]

# 置き場所の順番：列（左端＋上端がほぼ一定）ごとに、左の列から。列の中は下から上へ
dates.sort(key=lambda l: l.left + l.top)
cols, prev = [], None
for l in dates:
    k = l.left + l.top
    if prev is None or k - prev > 100:
        cols.append([])
    cols[-1].append(l); prev = k
positions = [l for col in cols for l in sorted(col, key=lambda l: -l.top)]

# 日付の一覧（元の日付＋新しい日付）→ 古いものを消して、古い順に
entries = []
for l in dates:
    dt, ht = parse(l.text)
    entries.append({'dt': dt, 'time': ht, 'text': fmt(dt, ht), 'src': l})
for s_ in NEW:
    dt, ht = parse(s_)
    entries.append({'dt': dt, 'time': ht, 'text': fmt(dt, ht), 'src': None})
entries.sort(key=lambda e: e['dt'])
removed = entries[:len(entries) - len(positions)]
entries = entries[len(entries) - len(positions):]
for e in removed:
    print('消す：', e['text'].replace('\r', ' '))

# 絵（文字の基準点からのずれ付き）を用意する
ref = positions[0]
ox_ref, oy_ref = ref.left - ref.transform[4], ref.top - ref.transform[5]
size_px = ref.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['FontSize'] * ref.transform[3]
by_text = {}
for l in dates:
    by_text.setdefault(fmt(*parse(l.text)), (true_pixels(l), l.left - l.transform[4], l.top - l.transform[5]))


def render(text):
    f = ImageFont.truetype(BOLD, round(size_px * SS), index=0)
    lines = text.split('\r')
    lead = round(size_px * 1.2 * SS)
    im = Image.new('RGBA', (max(f.getbbox(t)[2] for t in lines) + 8 * SS, lead * len(lines) + 8 * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, t in enumerate(lines):
        d.text((0, i * lead), t, font=f, fill=(0, 0, 0, 255))
    im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
    return im.crop(im.getbbox()), ox_ref, oy_ref


for e in entries:
    e['img'] = by_text[e['text']] if e['text'] in by_text else render(e['text'])
    e['drawn'] = e['text'] not in by_text

# 集計期間
mn, mx = entries[0]['dt'], entries[-1]['dt']
period_text = f'集計期間：{mn.year}年{mn.month}月{mn.day}日～{mx.year}年{mx.month}月{mx.day}日'

# ================= 編集できる PSD =================
for pos, e in zip(positions, entries):
    img, ox, oy = e['img']
    tx, ty = pos.transform[4], pos.transform[5]
    nl = replace_layer(psd, pos, img, round(tx + ox), round(ty + oy))
    set_text(nl, e['text'])
    print(f"({pos.left},{pos.top}) ←", e['text'].replace('\r', ' '), '（仮の絵）' if e['drawn'] else '')
p_box = None
if period is not None and period.text != period_text:
    sz = period.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']['FontSize'] * period.transform[3]
    f = ImageFont.truetype(REG, round(sz * SS), index=0)
    im = Image.new('RGBA', (f.getbbox(period_text)[2] + 8 * SS, round(sz * 1.6 * SS)), (230, 230, 230, 0))
    ImageDraw.Draw(im).text((4 * SS, 0), period_text, font=f, fill=(230, 230, 230, 255))
    im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
    pim = im.crop(im.getbbox())
    p_left = period.right - pim.width                 # 右端をそろえる
    p_box = (min(p_left, period.left) - 3, period.top - 3, period.right + 3, period.bottom + 3)
    nl = replace_layer(psd, period, pim, p_left, period.top)
    set_text(nl, period_text)
    from psd_tools.constants import Tag
    ts = nl.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
    xx, xy, yx, yy, tx, ty = ts.transform
    ts.transform = (xx, xy, yx, yy, tx + (p_left - period.left), ty)
print(period_text)

# ================= 確認用の画像 =================
tmp = out_psd + '.tmp.psd'
psd.save(tmp)
new_flat = PSDImage.open(tmp).composite(force=True).convert('RGB')   # 帯と日付（白フチ込み）は psd-tools でも正しく描ける
os.remove(tmp)
preview = flat.copy()
cb = (min(c.left for c in cards) - 4, min(c.top for c in cards) - 4, max(c.right for c in cards) + 4, max(c.bottom for c in cards) + 4)
preview.paste(new_flat.crop(cb), cb[:2])
if p_box:
    preview.paste(new_flat.crop(p_box), p_box[:2])
save_with_preview(psd, out_psd, preview)
preview.save(out_jpg, quality=95, subsampling=0)
print('保存', out_psd, out_jpg)
