// 楽天ランキングバナー 日付修正スクリプト（Photoshop / ExtendScript）
// 手順書：docs/楽天ランキングバナー修正マニュアル.md（第13章の流れをそのまま実装）
//
// 使い方（Windows / Mac 共通）：
//   Photoshop の［ファイル］→［スクリプト］→［参照...］でこのファイルを選ぶ。
//   ダイアログで「001で終わるPSD」（または、それが入ったフォルダ）を選ぶ。
//   同じフォルダに「元の名前(YYMMDD).psd / .jpg」を保存する。元ファイルは上書きしない。
//   同じフォルダに 001-002 などの合成PSDがあれば、1枚目を差し替えて保存する（第7章）。
//   処理ログは「ranking_fix_log(YYMMDD).txt」として同じフォルダに保存する。
//
// ※ このファイルは UTF-8（BOM付き）で保存すること（日本語の正規表現があるため）。

#target photoshop
app.bringToFront();

// ---------------- 設定 ----------------
var CFG = {
    FONT: "KozGoPr6N-Bold",       // 小塚ゴシック Pr6N Bold（第2-2節）
    SIZE: 0,                      // 0 = 日付の数から自動（第3-1節）。数値を入れるとその値に固定
    MIN_SIZE: 6,                  // 自動縮小の下限（pt）
    MOVE_UP: 8,                   // 標準の上移動（第2-3節）
    MARGIN: 5,                    // カード内の余白（第4-3節）
    WIDE: 1200,                   // これより広いキャンバスは最前面移動しない（第4-5節）
    CARD_W: [150, 1120],          // カード判定（第4-2節）
    CARD_H_MAX: 300,
    // ショップ名が画像に焼き込まれているカード用：ショップ名の右の空き開始位置（カード左端からのpx）
    // 「セレクトショップKK」のカード（幅約410px）は 213px。0 なら使わない。
    SHOP_FREE_X: 213,
    SHOP_CARD_W: [380, 440],      // SHOP_FREE_X を使うカード幅の範囲
    STROKE_PX: 2,                 // 白フチ（第3-2節）
    GLOW: true, GLOW_CHOKE: 1, GLOW_SIZE: 2,
    JPEG_QUALITY: 12
};

var WD = ["日", "月", "火", "水", "木", "金", "土"];
var LOG = [];
function log(s) { LOG.push(s); }

function pad2(n) { return (n < 10 ? "0" : "") + n; }
function today6() { var d = new Date(); return pad2(d.getFullYear() % 100) + pad2(d.getMonth() + 1) + pad2(d.getDate()); }
var TODAY = today6();

// 「xxx(260920)」の古い日付を外して今日の日付を付ける（第1-1節）
function datedName(name, ext) {
    var base = name.replace(/\.[^\.]+$/, "").replace(/\(\d{6}\)$/, "");
    return base + "(" + TODAY + ")." + ext;
}

// ---------------- 日付の解析と書式（第2-1節） ----------------
var RE_DATE = /(\d{4})\s*[\/年\.\-]\s*(\d{1,2})\s*[\/月\.\-]\s*(\d{1,2})\s*日?\s*(?:[\(（][^\)）]*[\)）])?\s*(?:(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*\d{2})?)?/;

function parseDate(text) {
    if (text.indexOf("集計期間") >= 0) return null;          // 絶対に対象外
    var m = RE_DATE.exec(text);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    var dt = new Date(y, mo - 1, d);
    if (dt.getMonth() != mo - 1) return null;
    var hasTime = (m[4] !== undefined && m[4] !== "" && m[4] != null);
    return { y: y, mo: mo, d: d, hasTime: hasTime, h: hasTime ? +m[4] : 0, mi: hasTime ? +m[5] : 0, date: dt };
}

function formatLines(p) {
    var wd = WD[p.date.getDay()];
    if (p.hasTime) {
        return ["リアルタイムランキング", p.y + "年" + p.mo + "月" + p.d + "日(" + wd + ") " + pad2(p.h) + ":" + pad2(p.mi) + "更新"];
    }
    var prev = new Date(p.y, p.mo - 1, p.d - 1);               // 集計日＝前日
    return ["デイリーランキング", p.y + "年" + p.mo + "月" + p.d + "日(" + wd + ")更新 (集計日：" + (prev.getMonth() + 1) + "月" + prev.getDate() + "日)"];
}

// ---------------- レイヤー補助 ----------------
function px(v) { return Math.round(v.as("px")); }
function rectOf(b) { return { l: px(b[0]), t: px(b[1]), r: px(b[2]), b: px(b[3]) }; }
function textRect(layer) {
    try { return rectOf(layer.boundsNoEffects); } catch (e) { return rectOf(layer.bounds); }
}
function overlap(a, b) {
    var w = Math.min(a.r, b.r) - Math.max(a.l, b.l), h = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    return (w > 0 && h > 0) ? w * h : 0;
}
// 上から順（手前→奥）にすべてのアートレイヤーを集める
function collect(container, out) {
    for (var i = 0; i < container.layers.length; i++) {
        var l = container.layers[i];
        if (l.typename == "LayerSet") collect(l, out); else out.push(l);
    }
    return out;
}
function selectLayer(layer) { app.activeDocument.activeLayer = layer; }

function hasStroke(layer) {
    selectLayer(layer);
    var ref = new ActionReference();
    ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    var d = executeActionGet(ref);
    var k = stringIDToTypeID("layerEffects");
    if (!d.hasKey(k)) return { stroke: false, fx: null };
    var fx = d.getObjectValue(k);
    return { stroke: fx.hasKey(charIDToTypeID("FrFX")), fx: fx };
}
function white() {
    var c = new ActionDescriptor();
    c.putDouble(charIDToTypeID("Rd  "), 255); c.putDouble(charIDToTypeID("Grn "), 255); c.putDouble(charIDToTypeID("Bl  "), 255);
    return c;
}
// 白フチ（既存があれば活かす）＋白い光彩（第3-2節）
function applyEffects(layer) {
    var st = hasStroke(layer);
    var fx = st.fx || new ActionDescriptor();
    fx.putUnitDouble(charIDToTypeID("Scl "), charIDToTypeID("#Prc"), 100);
    if (!st.stroke) {
        var s = new ActionDescriptor();
        s.putBoolean(charIDToTypeID("enab"), true);
        s.putEnumerated(charIDToTypeID("Styl"), charIDToTypeID("FStl"), charIDToTypeID("OutF"));
        s.putEnumerated(charIDToTypeID("PntT"), charIDToTypeID("FrFl"), charIDToTypeID("SClr"));
        s.putEnumerated(charIDToTypeID("Md  "), charIDToTypeID("BlnM"), charIDToTypeID("Nrml"));
        s.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), 100);
        s.putUnitDouble(charIDToTypeID("Sz  "), charIDToTypeID("#Pxl"), CFG.STROKE_PX);
        s.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), white());
        fx.putObject(charIDToTypeID("FrFX"), charIDToTypeID("FrFX"), s);
    }
    if (CFG.GLOW) {
        var g = new ActionDescriptor();
        g.putBoolean(charIDToTypeID("enab"), true);
        g.putEnumerated(charIDToTypeID("Md  "), charIDToTypeID("BlnM"), charIDToTypeID("Nrml"));
        g.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), white());
        g.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), 100);
        g.putEnumerated(charIDToTypeID("GlwT"), charIDToTypeID("BETE"), charIDToTypeID("SfBL"));
        g.putUnitDouble(charIDToTypeID("Ckmt"), charIDToTypeID("#Pxl"), CFG.GLOW_CHOKE);
        g.putUnitDouble(charIDToTypeID("blur"), charIDToTypeID("#Pxl"), CFG.GLOW_SIZE);
        g.putUnitDouble(charIDToTypeID("Nose"), charIDToTypeID("#Prc"), 0);
        g.putUnitDouble(charIDToTypeID("ShdN"), charIDToTypeID("#Prc"), 0);
        g.putBoolean(charIDToTypeID("AntA"), true);
        g.putUnitDouble(charIDToTypeID("Inpr"), charIDToTypeID("#Prc"), 50);
        fx.putObject(charIDToTypeID("OrGl"), charIDToTypeID("OrGl"), g);
    }
    var desc = new ActionDescriptor(), ref = new ActionReference();
    ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Lefx"));
    ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    desc.putReference(charIDToTypeID("null"), ref);
    desc.putObject(charIDToTypeID("T   "), charIDToTypeID("Lefx"), fx);
    executeAction(charIDToTypeID("setd"), desc, DialogModes.NO);
    return st.stroke ? "既存フチを維持" : "白フチ追加";
}

// 文字の書式（第2-2節・第5章）
function styleText(layer, lines, size, oneLine) {
    var t = layer.textItem;
    t.contents = oneLine ? lines.join(" ") : lines.join("\r");
    t.font = CFG.FONT;
    t.fauxBold = false;
    t.fauxItalic = false;
    var c = new SolidColor(); c.rgb.hexValue = "000000"; t.color = c;
    t.size = new UnitValue(size, "pt");
    // 内容を書き換えると段落設定がリセットされることがあるので、毎回設定し直す
    t.useAutoLeading = true;
    try { t.spaceBefore = new UnitValue(0, "pt"); } catch (e) {}
    try { t.spaceAfter = new UnitValue(0, "pt"); } catch (e) {}
    setLeadingBelow(layer);
}
// leadingType = leadingBelow（段落の行送り基準）
function setLeadingBelow(layer) {
    try {
        selectLayer(layer);
        var d = new ActionDescriptor(), ref = new ActionReference();
        ref.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("paragraphStyle"));
        ref.putEnumerated(charIDToTypeID("TxLr"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        d.putReference(charIDToTypeID("null"), ref);
        var ps = new ActionDescriptor();
        ps.putInteger(stringIDToTypeID("textOverrideFeatureName"), 808464438);
        ps.putEnumerated(stringIDToTypeID("leadingType"), stringIDToTypeID("leadingType"), stringIDToTypeID("leadingBelow"));
        ps.putUnitDouble(stringIDToTypeID("spaceBefore"), charIDToTypeID("#Pnt"), 0);
        d.putObject(charIDToTypeID("T   "), stringIDToTypeID("paragraphStyle"), ps);
        executeAction(charIDToTypeID("setd"), d, DialogModes.NO);
    } catch (e) { log("  (段落設定 leadingBelow は省略: " + e + ")"); }
}

function moveTo(layer, left, top) {
    var r = textRect(layer);
    var dx = left - r.l, dy = top - r.t;
    if (dx || dy) layer.translate(new UnitValue(dx, "px"), new UnitValue(dy, "px"));
}

function autoSize(n) {           // 第3-1節の目安
    if (n <= 4) return 13;
    if (n <= 11) return 12;
    if (n <= 30) return 10;
    return 9;
}

// ---------------- 保存（第1-2節） ----------------
function checkActive(expect) {
    if (app.documents.length < 1) throw new Error("ABORT: ドキュメントが開いていません");
    var doc = app.activeDocument;
    if (doc.name != expect) throw new Error("ABORT: アクティブなドキュメントが '" + doc.name + "'（期待：'" + expect + "'）なので保存を中止しました");
    return doc;
}
function savePSD(doc, expectName, file) {
    checkActive(expectName);
    var so = new PhotoshopSaveOptions(); so.layers = true; so.embedColorProfile = true;
    doc.saveAs(file, so, false, Extension.LOWERCASE);   // saveAs 後、doc.name は新しい名前になる
}
function saveJPEG(doc, expectName, file) {
    checkActive(expectName);
    var jo = new JPEGSaveOptions();
    jo.quality = CFG.JPEG_QUALITY; jo.embedColorProfile = true;
    jo.formatOptions = FormatOptions.STANDARDBASELINE; jo.matte = MatteType.NONE;
    doc.saveAs(file, jo, true, Extension.LOWERCASE);    // asCopy
}

function closeAll() {
    while (app.documents.length) app.activeDocument.close(SaveOptions.PROMPTTOSAVECHANGES);
    if (app.documents.length) throw new Error("ABORT: 閉じられなかったドキュメントがあります");
}
function openOnly(file) {
    closeAll();
    var doc = app.open(file);
    if (app.documents.length != 1 || doc.name != file.name) throw new Error("ABORT: 開いたファイルが想定と違います（" + doc.name + "）");
    return doc;
}

// ---------------- 001 の編集（第13章 1〜12） ----------------
function processBanner(file) {
    var outPsd = new File(file.parent + "/" + datedName(file.name, "psd"));
    var outJpg = new File(file.parent + "/" + datedName(file.name, "jpg"));
    if (outPsd.exists) { log("スキップ：" + outPsd.name + " はすでに存在します"); return null; }

    var doc = openOnly(file);
    var W = px(doc.width);
    var all = collect(doc, []);

    // 日付以外のレイヤー位置を記録（第2-4節の確認用）
    var before = [];
    for (var i = 0; i < all.length; i++) before.push({ layer: all[i], r: rectOf(all[i].bounds) });

    // 日付レイヤーとカードの検出
    var dates = [], cards = [], period = null;
    for (i = 0; i < all.length; i++) {
        var l = all[i];
        if (l.kind == LayerKind.TEXT) {
            var txt = l.textItem.contents;
            if (txt.indexOf("集計期間") >= 0) { period = l; continue; }
            var p = parseDate(txt);
            if (p) dates.push({ layer: l, p: p, orig: textRect(l), wasHidden: !l.visible, old: txt });
        } else if (l.kind == LayerKind.NORMAL && l.visible) {
            var r = rectOf(l.bounds), w = r.r - r.l, h = r.b - r.t;
            if (w >= CFG.CARD_W[0] && w <= CFG.CARD_W[1] && h < CFG.CARD_H_MAX) cards.push({ layer: l, r: r, z: i });
        }
    }
    log("■ " + file.name + "：日付 " + dates.length + " 件、カード " + cards.length + " 枚");
    if (dates.length != cards.length) log("  ！日付とカードの数が違います（第4-6節の確認が必要）");

    var size = CFG.SIZE || autoSize(dates.length);
    var front = (W <= CFG.WIDE);

    // 書式・リンク解除・元の左上へ戻す・8px上・最前面（第2章）
    for (i = 0; i < dates.length; i++) {
        var D = dates[i];
        try { D.layer.unlink(); } catch (e) {}                    // 動かす前に必ずリンク解除
        if (D.wasHidden) D.layer.visible = true;                  // 隠れた日付は表示（第4-6節）
        D.lines = formatLines(D.p);
        styleText(D.layer, D.lines, size, false);
        moveTo(D.layer, D.orig.l, D.orig.t - CFG.MOVE_UP);
        if (front) {
            var parent = D.layer.parent;
            if (parent.layers[0] != D.layer) D.layer.move(parent.layers[0], ElementPlacement.PLACEBEFORE);
        }
    }

    // カードの割り当てと、見えている範囲（手前のカードに隠れない範囲）の計算（第4章）
    for (i = 0; i < dates.length; i++) {
        D = dates[i];
        var tr = textRect(D.layer), best = null, bestA = 0;
        for (var c = 0; c < cards.length; c++) {
            var a = overlap(tr, cards[c].r);
            if (a > bestA) { bestA = a; best = cards[c]; }
        }
        if (!best) {                                              // 対応カードなし → 非表示（削除しない）
            D.layer.visible = false; D.noCard = true;
            log("  ！対応するカードがないため非表示：" + D.old);
            continue;
        }
        var cr = best.r, cw = cr.r - cr.l;
        var box = { l: cr.l + CFG.MARGIN, t: cr.t + CFG.MARGIN, r: cr.r - CFG.MARGIN, b: cr.b - CFG.MARGIN };
        var x0 = D.orig.l;
        if (CFG.SHOP_FREE_X && cw >= CFG.SHOP_CARD_W[0] && cw <= CFG.SHOP_CARD_W[1]) x0 = Math.max(x0, cr.l + CFG.SHOP_FREE_X);  // 第4-4節
        x0 = Math.max(x0, box.l);
        // このカードより手前にあるカードで隠れる部分を除く
        for (c = 0; c < cards.length; c++) {
            var o = cards[c];
            if (o.z >= best.z || !overlap(o.r, cr)) continue;
            if (o.r.l <= x0 + 10 && o.r.b > box.t) box.t = Math.max(box.t, o.r.b + 1);   // 上側を覆うカード
        }
        for (c = 0; c < cards.length; c++) {
            o = cards[c];
            if (o.z >= best.z || !overlap(o.r, cr)) continue;
            if (o.r.l > x0 && o.r.t < box.b && o.r.b > box.t) box.r = Math.min(box.r, o.r.l - 3);          // 右側を覆うカード
        }
        D.box = box; D.x0 = x0;
    }

    // 文字サイズの決定：全件が見えている範囲に収まる最大サイズ（全件同じサイズにそろえる）
    var oneLine = false;
    function fits(s, one) {
        for (var k = 0; k < dates.length; k++) {
            var E = dates[k]; if (E.noCard) continue;
            styleText(E.layer, E.lines, s, one);
            var r = textRect(E.layer);
            if (r.r - r.l > E.box.r - E.x0 || r.b - r.t > E.box.b - E.box.t) return false;
        }
        return true;
    }
    var s = size;
    while (s > CFG.MIN_SIZE && !fits(s, false)) s -= 0.5;
    if (!fits(s, false)) {                                        // 第9章：1行にまとめる例外
        var s1 = size;
        while (s1 > CFG.MIN_SIZE && !fits(s1, true)) s1 -= 0.5;
        if (fits(s1, true) && s1 > s) { s = s1; oneLine = true; }
        else fits(s, false);
    }
    if (oneLine) log("  ※重なりが避けられないデザインのため1行フォーマットに変更");
    if (s != size) log("  文字サイズ：目安 " + size + "pt → 枠に収めるため " + s + "pt");
    else log("  文字サイズ：" + s + "pt");

    // 配置：元の左上（8px上）を基準に、見えている範囲へクランプ（第4-3・4-4節）＋効果
    var periodMin = null, periodMax = null, rt = 0, dl = 0;
    for (i = 0; i < dates.length; i++) {
        D = dates[i];
        if (D.p.hasTime) rt++; else dl++;
        if (!periodMin || D.p.date < periodMin.date) periodMin = D.p;
        if (!periodMax || D.p.date > periodMax.date) periodMax = D.p;
        if (D.noCard) continue;
        var r2 = textRect(D.layer), tw = r2.r - r2.l, th = r2.b - r2.t;
        var L = Math.max(D.x0, Math.min(D.orig.l, D.box.r - tw));
        var T = D.orig.t - CFG.MOVE_UP;
        T = Math.max(D.box.t, Math.min(T, D.box.b - th));
        moveTo(D.layer, L, T);
        var fxNote = applyEffects(D.layer);
        log("  " + D.old.replace(/[\r\n]/g, " ") + " → " + D.lines.join(" / ") + (D.wasHidden ? "（非表示→表示）" : "") + "（" + fxNote + "）");
    }
    log("  内訳：リアルタイム " + rt + " 件・デイリー " + dl + " 件");

    // 集計期間（第6章）
    if (period && periodMin) {
        var np = "集計期間：" + periodMin.y + "年" + periodMin.mo + "月" + periodMin.d + "日～" + periodMax.y + "年" + periodMax.mo + "月" + periodMax.d + "日";
        if (period.textItem.contents == np) log("  集計期間：変更なし");
        else {
            var pr = textRect(period);
            period.textItem.contents = np;
            var pr2 = textRect(period);
            moveTo(period, pr.r - (pr2.r - pr2.l), pr.t);          // 右端をそろえる
            log("  集計期間：→ " + np);
        }
    }

    // 日付以外のレイヤーが動いていないか（第2-4節）
    var moved = 0;
    for (i = 0; i < before.length; i++) {
        var B = before[i], isDate = (B.layer == period);
        for (var j = 0; j < dates.length && !isDate; j++) if (dates[j].layer == B.layer) isDate = true;
        if (isDate) continue;
        var nr = rectOf(B.layer.bounds);
        if (nr.l != B.r.l || nr.t != B.r.t || nr.r != B.r.r || nr.b != B.r.b) { moved++; log("  ！位置が変わったレイヤー：" + B.layer.name); }
    }
    if (moved) throw new Error("ABORT: 日付以外のレイヤーが動いたため保存しません（" + moved + "件）");
    log("  日付以外のレイヤーの位置：変化なし");

    // 保存（第1-2節）
    savePSD(doc, file.name, outPsd);
    saveJPEG(doc, outPsd.name, outJpg);
    log("  保存：" + outPsd.name + " / " + outJpg.name + "（元ファイルは変更なし）");
    closeAll();
    return outJpg;
}

// ---------------- 合成データへの差し替え（第7章） ----------------
function processComposite(file, jpg) {
    var outPsd = new File(file.parent + "/" + datedName(file.name, "psd"));
    var outJpg = new File(file.parent + "/" + datedName(file.name, "jpg"));
    if (outPsd.exists) { log("スキップ：" + outPsd.name + " はすでに存在します"); return; }
    var doc = openOnly(file);
    var all = collect(doc, []), target = null;
    for (var i = 0; i < all.length; i++) {
        var l = all[i];
        if (l.kind != LayerKind.NORMAL && l.kind != LayerKind.SMARTOBJECT) continue;
        var r = rectOf(l.bounds), w = r.r - r.l, h = r.b - r.t;
        if (w < 600 || Math.abs(r.t) > 20 || Math.abs(r.l) > 20 || h > px(doc.height) * 0.9) continue;
        // 手前に重なるレイヤーがある画像（例：001部分がレイヤーのままの合成の「背景」）は差し替えても見えないので対象外
        var covered = false;
        for (var j = 0; j < i && !covered; j++) {
            if (all[j].visible && overlap(rectOf(all[j].bounds), r) > w * h * 0.1) covered = true;
        }
        if (covered) { log("  （" + l.name + " は手前に別のレイヤーが重なっているため差し替え対象外）"); continue; }
        if (!target || r.t < target.r.t) target = { layer: l, r: r };
    }
    if (!target) { log("  ！" + file.name + "：差し替え対象（上端の幅600px以上の画像）が見つからないので触っていません"); closeAll(); return; }
    log("■ 合成：" + file.name + " の「" + target.layer.name + "」(" + target.r.l + "," + target.r.t + "," + target.r.r + "," + target.r.b + ") を差し替え");

    if (target.layer.kind == LayerKind.SMARTOBJECT) {
        selectLayer(target.layer);
        var d = new ActionDescriptor(); d.putPath(charIDToTypeID("null"), jpg);
        executeAction(stringIDToTypeID("placedLayerReplaceContents"), d, DialogModes.NO);
    } else {
        var src = app.open(jpg);
        src.selection.selectAll(); src.selection.copy();
        src.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = doc;
        if (app.activeDocument.name != file.name) throw new Error("ABORT: アクティブなドキュメントが合成PSDではありません");
        selectLayer(target.layer);
        var pasted = doc.paste();
        pasted.name = target.layer.name;
        var pr = rectOf(pasted.bounds);
        pasted.translate(new UnitValue(target.r.l - pr.l, "px"), new UnitValue(target.r.t - pr.t, "px"));
        target.layer.remove();
        target.layer = pasted;
    }
    var nr = rectOf(target.layer.bounds);
    if (nr.t != 0) target.layer.translate(new UnitValue(0, "px"), new UnitValue(-nr.t, "px"));   // 上端ぴったり
    savePSD(doc, file.name, outPsd);
    saveJPEG(doc, outPsd.name, outJpg);
    log("  保存：" + outPsd.name + " / " + outJpg.name + "（★最終jpeg。2枚目以降は変更なし）");
    closeAll();
}

// ---------------- メイン ----------------
function main() {
    var pick = File.openDialog("001で終わるPSDを選んでください（キャンセルでフォルダ選択）", "*.psd");
    var files = [], folder;
    if (pick) { files.push(pick); folder = pick.parent; }
    else {
        folder = Folder.selectDialog("001で終わるデータが入ったフォルダを選んでください");
        if (!folder) return;
        var list = folder.getFiles("*.psd");
        for (var i = 0; i < list.length; i++) {
            if (/001(\(\d{6}\))?\.psd$/i.test(list[i].name) && !/-\d{3}(\(\d{6}\))?\.psd$/i.test(list[i].name)) files.push(list[i]);
        }
    }
    if (!files.length) { alert("001で終わるPSDが見つかりません"); return; }
    if (app.documents.length && !confirm("開いているドキュメントをすべて閉じてから作業します（未保存のものは保存するか聞かれます）。よろしいですか？")) return;

    var oldRuler = app.preferences.rulerUnits, oldType = app.preferences.typeUnits;
    app.preferences.rulerUnits = Units.PIXELS; app.preferences.typeUnits = TypeUnits.POINTS;
    try {
        var lastJpg = null;
        for (var f = 0; f < files.length; f++) lastJpg = processBanner(files[f]) || lastJpg;
        // 合成データ（001-002 など）
        if (lastJpg) {
            var comps = folder.getFiles(function (x) { return x instanceof File && /001-\d{3}.*\.psd$/i.test(x.name) && !/\(\d{6}\)\.psd$/i.test(x.name); });
            if (!comps.length) log("合成データ（001-002 など）は見つかりませんでした");
            for (var k = 0; k < comps.length; k++) processComposite(comps[k], lastJpg);
        }
    } catch (e) {
        log("エラー：" + e.message + (e.line ? "（" + e.line + "行目）" : ""));
    } finally {
        app.preferences.rulerUnits = oldRuler; app.preferences.typeUnits = oldType;
        var lf = new File(folder + "/ranking_fix_log(" + TODAY + ").txt");
        lf.encoding = "UTF-8"; lf.open("w"); lf.write(LOG.join("\n")); lf.close();
        alert(LOG.join("\n").substring(0, 3000));
    }
}
main();
