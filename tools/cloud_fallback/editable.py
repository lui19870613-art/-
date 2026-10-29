"""あとで Photoshop で手を加えられる PSD を作るための補助（psd-tools）。

既存レイヤーを「同じ設定のまま、絵（ピクセル）と位置・大きさだけ差し替えた新しいレイヤー」に置き換える。
- 元レイヤーの付加情報（文字の設定 TySh・レイヤー効果 lfx2・名前・ID など）をそのまま引き継ぐので、
  文字レイヤーは文字のまま（フォント・効果も元のまま）、画像レイヤーは画像のまま残る。
- 文字レイヤーは変形情報（transform）も同じ倍率・位置に直すので、Photoshop で文字を打ち直しても同じ場所に出る。
- 効果（白フチ・影）は Photoshop が描くので、拡大しても効果の太さは元のまま。

注意：psd-tools の合成（composite）はドロップシャドウを描かない。仕上がり確認用の JPEG は別に描くこと。
"""
import copy
from PIL import Image
from psd_tools.api.layers import PixelLayer
from psd_tools.constants import Tag, Compression, ChannelID


def new_pixel_layer(psd, img, left, top, append=True):
    """透明な部分を「透明チャンネル」として持つ画像レイヤーを作る。
    psd-tools の frompil は RGB モードの PSD だと透明を「黒い四角＋レイヤーマスク」にしてしまい、
    Photoshop で文字を打ち直したときにマスクで欠けるので使わない。"""
    img = img.convert('RGBA')
    rec, chans = PixelLayer._build_layer_record_and_channels(
        img, 'tmp', left, top, Compression.RLE,
        version=psd._record.header.version, depth=psd._record.header.depth)
    ids = [c.id for c in rec.channel_info]
    assert ChannelID.TRANSPARENCY_MASK in ids and ChannelID.USER_LAYER_MASK not in ids, ids
    nl = PixelLayer(psd, rec, chans)
    if append:
        psd.append(nl)
    return nl


def replace_layer(psd, old, img, left, top, parent=None):
    """old を、img を絵にした新しいレイヤーに置き換える（設定は old のまま）。新しいレイヤーを返す。"""
    parent = parent or old.parent
    nl = new_pixel_layer(psd, img, left, top, append=False)
    rec, orec = nl._record, old._record
    rec.tagged_blocks = copy.deepcopy(orec.tagged_blocks)      # 文字・効果・名前・ID などを引き継ぐ
    rec.name = orec.name
    rec.blend_mode, rec.opacity, rec.clipping = orec.blend_mode, orec.opacity, orec.clipping
    rec.flags = copy.deepcopy(orec.flags)
    idx = parent.index(old)
    parent.remove(old)
    parent.insert(idx, nl)
    return nl


def true_pixels(layer):
    """レイヤーの絵を、透明を正しく持った RGBA で返す。
    以前の psd-tools の出力で「黒い四角＋レイヤーマスク」になっているものは、マスクを透明に戻す。"""
    im = layer.topil()
    if im is None:
        return None
    im = im.convert('RGBA')
    if layer.has_mask() and im.getchannel('A').getextrema() == (255, 255):
        m = layer.mask
        alpha = Image.new('L', im.size, m.background_color)
        mi = m.topil()
        if mi is not None:
            alpha.paste(mi.convert('L'), (m.left - layer.left, m.top - layer.top))
        im.putalpha(alpha)
    return im


def is_broken(layer):
    """「黒い四角＋レイヤーマスク」になっているレイヤーか。"""
    if layer.is_group() or not layer.has_mask():
        return False
    im = layer.topil()
    return im is not None and im.convert('RGBA').getchannel('A').getextrema() == (255, 255)


def repair(psd):
    """「黒い四角＋レイヤーマスク」になったレイヤーを、透明チャンネルを持つ元の形に直す。直した数を返す。"""
    n = 0
    for l in list(psd.descendants()):
        if is_broken(l):
            replace_layer(psd, l, true_pixels(l), l.left, l.top)
            n += 1
    return n


def scaled_image(layer, s):
    im = true_pixels(layer)
    if im is None:
        return None
    im = im.convert('RGBA')
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)


def scale_text_transform(layer_record_owner, s, ox, oy, nx, ny):
    """文字の変形情報を、(ox,oy) を (nx,ny) に移して s 倍にする。"""
    ts = layer_record_owner.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
    xx, xy, yx, yy, tx, ty = ts.transform
    ts.transform = (xx * s, xy * s, yx * s, yy * s, nx + (tx - ox) * s, ny + (ty - oy) * s)


def move_scale(psd, layer, s, ox, oy, nx, ny):
    """layer を、点 (ox,oy) が (nx,ny) に来るように s 倍して置き換える。新しいレイヤーを返す。"""
    img = scaled_image(layer, s)
    left = round(nx + (layer.left - ox) * s)
    top = round(ny + (layer.top - oy) * s)
    is_text = layer.kind == 'type'
    nl = replace_layer(psd, layer, img, left, top)
    if is_text:
        scale_text_transform(nl, s, ox, oy, nx, ny)
    return nl


def set_text(layer, text):
    """文字レイヤーの文字を書き換える。書式は1種類、段落は「行ごとに1つ」または「全体で1つ」の文字に対応。
    改行は '\r'。絵は別に replace_layer で差し替えること。"""
    ts = layer.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
    td = ts.text_data
    td[b'Txt '].value = text + '\x00'
    e = td[b'EngineData'].value['EngineDict']
    e['Editor']['Text'].value = text + '\r'
    total = len(text) + 1
    lines = text.split('\r')

    def setlen(arr, values):
        for i, v in enumerate(values):
            arr[i] = type(arr[i])(v) if not isinstance(arr[i], int) else v

    arr = e['StyleRun']['RunLengthArray']
    if len(arr) != 1:
        raise ValueError('書式（StyleRun）が複数あるため書き換えできません')
    setlen(arr, [total])
    arr = e['ParagraphRun']['RunLengthArray']
    if len(arr) == 1:
        setlen(arr, [total])
    elif len(arr) == len(lines):
        setlen(arr, [len(t) + 1 for t in lines])          # 各行の文字数＋改行
    else:
        raise ValueError(f'段落の数（{len(arr)}）と行の数（{len(lines)}）が合いません')


def save_with_preview(psd, path, preview):
    """PSD を保存する。埋め込みプレビュー（Photoshop 以外のアプリや縮小表示で見える1枚絵）を preview（PIL 画像）にする。
    psd-tools が作るプレビューは影を描かないため、仕上がり確認用に描いた画像を入れる。"""
    import numpy as np
    from psd_tools.api import numpy_io
    arr = np.asarray(preview.convert('RGB'), dtype=np.float32) / 255.0
    alpha = np.ones(arr.shape[:2] + (1,), dtype=np.float32)

    def _update_preview():
        psd._record.image_data.set_data(numpy_io.encode_image_data(psd, arr, alpha), psd._record.header)
    psd._update_preview = _update_preview
    psd.save(path)
