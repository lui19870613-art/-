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
from psd_tools.constants import Tag


def replace_layer(psd, old, img, left, top, parent=None):
    """old を、img を絵にした新しいレイヤーに置き換える（設定は old のまま）。新しいレイヤーを返す。"""
    parent = parent or old.parent
    nl = PixelLayer.frompil(img, psd, 'tmp', top, left)
    rec, orec = nl._record, old._record
    rec.tagged_blocks = copy.deepcopy(orec.tagged_blocks)      # 文字・効果・名前・ID などを引き継ぐ
    rec.name = orec.name
    rec.blend_mode, rec.opacity, rec.clipping = orec.blend_mode, orec.opacity, orec.clipping
    rec.flags = copy.deepcopy(orec.flags)
    idx = parent.index(old)
    parent.remove(old)
    parent.insert(idx, nl)
    return nl


def scaled_image(layer, s):
    im = layer.topil()
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
    """文字レイヤーの文字を書き換える（1つの書式だけの文字に対応）。絵は別に replace_layer で差し替えること。"""
    ts = layer.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
    td = ts.text_data
    td[b'Txt '].value = text + '\x00'
    e = td[b'EngineData'].value['EngineDict']
    e['Editor']['Text'].value = text + '\r'
    n = len(text) + 1
    for run in ('StyleRun', 'ParagraphRun'):
        arr = e[run]['RunLengthArray']
        if len(arr) != 1:
            raise ValueError(f'{run} が複数あるため書き換えできません')
        arr[0] = type(arr[0])(n) if not isinstance(arr[0], int) else n


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
