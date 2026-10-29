// 帯（カード）の枚数を減らすスクリプト（Photoshop / ExtendScript）
// 例：「cardを20個にして」→ 日付が古い列から順に、帯と日付を列ごと削除し、
//     残った帯と日付を同じ倍率で拡大して、元の帯の範囲（横幅）を埋めるように中央へ並べ直す。
//     集計期間は残った日付の最初～最後に更新する（マニュアル第6章）。
//
// 使い方：Photoshop の［ファイル］→［スクリプト］→［参照...］でこのファイルを選び、PSD を選ぶ。
//   同じフォルダに「元の名前(YYMMDD).psd / .jpg」を保存する。元ファイルは上書きしない（第1章）。
//   ログ「cards_log(YYMMDD).txt」を同じフォルダに保存する。
// ※ UTF-8（BOM付き）で保存すること。

#target photoshop
app.bringToFront();

var CFG = {
    COUNT: 20,                 // 残す帯の枚数（起動時に聞く）
    CARD_W: [150, 1120],       // カード判定（第4-2節）。メダル画像（正方形）を外すため高さは150px未満にする
    CARD_H_MAX: 150,
    COL_GAP: 100,              // 「左端＋上端」の値がこれ以上離れていたら別の列
    TOP_TEXT: "たくさん",       // 帯の上にある文字（この下端より下に収める）
    BOTTOM_TEXT: "在庫",        // 帯の下にある文字（この上端より上に収める）
    PAD: 6,
    JPEG_QUALITY: 12
};

var LOG = [];
function log(s) { LOG.push(s); }
function pad2(n) { return (n < 10 ? "0" : "") + n; }
var TODAY = (function () { var d = new Date(); return pad2(d.getFullYear() % 100) + pad2(d.getMonth() + 1) + pad2(d.getDate()); })();

// 「xxx(261002)」や「xxx001261002」のような古い日付を外して、今日の日付を付ける（第1-1節）
function datedName(name, ext) {
    var base = name.replace(/\.[^\.]+$/, "").replace(/\(\d{6}\)$/, "").replace(/(001)\d{6}$/, "$1");
    return base + "(" + TODAY + ")." + ext;
}

var RE_DATE = /(\d{4})\s*[\/年\.\-]\s*(\d{1,2})\s*[\/月\.\-]\s*(\d{1,2})/;
function parseDate(text) {
    if (text.indexOf("集計期間") >= 0) return null;
    var m = RE_DATE.exec(text);
    if (!m) return null;
    return { y: +m[1], mo: +m[2], d: +m[3], date: new Date(+m[1], +m[2] - 1, +m[3]) };
}

function px(v) { return Math.round(v.as("px")); }
function rectOf(b) { return { l: px(b[0]), t: px(b[1]), r: px(b[2]), b: px(b[3]) }; }
function textRect(l) { try { return rectOf(l.boundsNoEffects); } catch (e) { return rectOf(l.bounds); } }
function collect(container, out) {
    for (var i = 0; i < container.layers.length; i++) {
        var l = container.layers[i];
        if (l.typename == "LayerSet") collect(l, out); else out.push(l);
    }
    return out;
}
function checkActive(expect) {
    if (app.documents.length < 1) throw new Error("ABORT: ドキュメントが開いていません");
    if (app.activeDocument.name != expect) throw new Error("ABORT: アクティブなドキュメントが '" + app.activeDocument.name + "'（期待：'" + expect + "'）なので保存を中止しました");
    return app.activeDocument;
}
function closeAll() { while (app.documents.length) app.activeDocument.close(SaveOptions.PROMPTTOSAVECHANGES); }

function run(file, count) {
    var outPsd = new File(file.parent + "/" + datedName(file.name, "psd"));
    var outJpg = new File(file.parent + "/" + datedName(file.name, "jpg"));
    if (outPsd.exists) { log("スキップ：" + outPsd.name + " はすでに存在します"); return; }

    closeAll();
    var doc = app.open(file);
    if (app.documents.length != 1 || doc.name != file.name) throw new Error("ABORT: 開いたファイルが想定と違います（" + doc.name + "）");
    var all = collect(doc, []);

    var before = [];
    for (var i = 0; i < all.length; i++) before.push({ layer: all[i], r: rectOf(all[i].bounds) });

    // 帯・日付・目印の文字
    var cards = [], dates = [], period = null, topText = null, bottomText = null;
    for (i = 0; i < all.length; i++) {
        var l = all[i];
        if (l.kind == LayerKind.TEXT) {
            var t = l.textItem.contents;
            if (t.indexOf("集計期間") >= 0) { period = l; continue; }
            if (t.indexOf(CFG.TOP_TEXT) == 0) topText = l;
            if (t.indexOf(CFG.BOTTOM_TEXT) == 0) bottomText = l;
            var p = parseDate(t);
            if (p) dates.push({ layer: l, p: p, r: textRect(l) });
        } else if (l.kind == LayerKind.NORMAL && l.visible) {
            var r = rectOf(l.bounds), w = r.r - r.l, h = r.b - r.t;
            if (w >= CFG.CARD_W[0] && w <= CFG.CARD_W[1] && h < CFG.CARD_H_MAX) cards.push({ layer: l, r: r, z: i });
        }
    }
    log("■ " + file.name + "：帯 " + cards.length + " 枚、日付 " + dates.length + " 件");
    if (cards.length <= count) { log("  帯はすでに " + cards.length + " 枚なので何もしません"); closeAll(); return; }

    // 列分け（斜めに並ぶ帯は「左端＋上端」がほぼ一定）
    cards.sort(function (a, b) { return (a.r.l + a.r.t) - (b.r.l + b.r.t); });
    var cols = [], cur = null, prevKey = null;
    for (i = 0; i < cards.length; i++) {
        var key = cards[i].r.l + cards[i].r.t;
        if (prevKey === null || key - prevKey > CFG.COL_GAP) { cur = { cards: [], dates: [], newest: null }; cols.push(cur); }
        cur.cards.push(cards[i]); cards[i].col = cur; prevKey = key;
    }
    // 日付 → 帯（日付を丸ごと含む帯のうち、いちばん手前）
    for (i = 0; i < dates.length; i++) {
        var D = dates[i], best = null;
        for (var c = 0; c < cards.length; c++) {
            var cr = cards[c].r;
            if (cr.l <= D.r.l && cr.t <= D.r.t && cr.r >= D.r.r && cr.b >= D.r.b && (!best || cards[c].z < best.z)) best = cards[c];
        }
        if (!best) { log("  ！帯が見つからない日付：" + D.layer.textItem.contents.replace(/\r/g, " ")); continue; }
        D.card = best; best.col.dates.push(D);
        if (!best.col.newest || D.p.date > best.col.newest) best.col.newest = D.p.date;
    }
    var colInfo = [];
    for (i = 0; i < cols.length; i++) colInfo.push("列" + (i + 1) + "：帯 " + cols[i].cards.length + " 枚・日付 " + cols[i].dates.length + " 件");
    log("  " + colInfo.join(" / "));

    // 古い列から削除（列の途中では切らない）
    var order = cols.slice().sort(function (a, b) { return (a.newest || 0) - (b.newest || 0); });
    var remain = cards.length, drop = [];
    for (i = 0; i < order.length && remain > count; i++) { drop.push(order[i]); remain -= order[i].cards.length; }
    if (remain != count) throw new Error("ABORT: 列ごとに消すと " + remain + " 枚になり、" + count + " 枚ちょうどにできません（どの帯を消すか指示が必要です）");

    var keepCards = [], keepDates = [], oldX0 = 1e9, oldX1 = -1e9, oldY0 = 1e9, oldY1 = -1e9;
    for (i = 0; i < cards.length; i++) {
        oldX0 = Math.min(oldX0, cards[i].r.l); oldX1 = Math.max(oldX1, cards[i].r.r);
        oldY0 = Math.min(oldY0, cards[i].r.t); oldY1 = Math.max(oldY1, cards[i].r.b);
    }
    var removed = [];
    for (i = 0; i < drop.length; i++) {
        for (c = 0; c < drop[i].dates.length; c++) { removed.push(drop[i].dates[c].layer); }
        for (c = 0; c < drop[i].cards.length; c++) { removed.push(drop[i].cards[c].layer); }
        log("  削除：日付が古い列（最新の日付 " + drop[i].newest.getFullYear() + "/" + (drop[i].newest.getMonth() + 1) + "/" + drop[i].newest.getDate() + "）の帯 " + drop[i].cards.length + " 枚・日付 " + drop[i].dates.length + " 件");
    }
    for (i = 0; i < cols.length; i++) {
        var isDrop = false;
        for (c = 0; c < drop.length; c++) if (drop[c] == cols[i]) isDrop = true;
        if (isDrop) continue;
        for (c = 0; c < cols[i].cards.length; c++) keepCards.push(cols[i].cards[c]);
        for (c = 0; c < cols[i].dates.length; c++) keepDates.push(cols[i].dates[c]);
    }

    // 残す帯の範囲と、拡大後の範囲
    var ux0 = 1e9, uy0 = 1e9, ux1 = -1e9, uy1 = -1e9;
    for (i = 0; i < keepCards.length; i++) {
        var k = keepCards[i].r;
        ux0 = Math.min(ux0, k.l); uy0 = Math.min(uy0, k.t); ux1 = Math.max(ux1, k.r); uy1 = Math.max(uy1, k.b);
    }
    var topLim = topText ? rectOf(topText.bounds).b + CFG.PAD : oldY0;
    var botLim = bottomText ? rectOf(bottomText.bounds).t - CFG.PAD : oldY1;
    var s = Math.min((oldX1 - oldX0) / (ux1 - ux0), (botLim - topLim) / (uy1 - uy0));
    var nx0 = (oldX0 + oldX1) / 2 - (ux1 - ux0) * s / 2;
    var ny0 = topLim + ((botLim - topLim) - (uy1 - uy0) * s) / 2;
    log("  拡大：" + Math.round(s * 1000) / 10 + "%（横 " + oldX0 + "～" + oldX1 + "・縦 " + Math.round(topLim) + "～" + Math.round(botLim) + " に収まる最大）");

    // 削除（動かす・消す前にリンク解除：第2-4節）
    for (i = 0; i < removed.length; i++) { try { removed[i].unlink(); } catch (e) {} }
    for (i = 0; i < removed.length; i++) removed[i].remove();

    // 拡大して並べ直す
    var moveList = [];
    for (i = 0; i < keepCards.length; i++) moveList.push({ layer: keepCards[i].layer, r: keepCards[i].r, text: false });
    for (i = 0; i < keepDates.length; i++) moveList.push({ layer: keepDates[i].layer, r: keepDates[i].r, text: true });
    for (i = 0; i < moveList.length; i++) {
        var M = moveList[i];
        try { M.layer.unlink(); } catch (e) {}
        M.layer.resize(s * 100, s * 100, AnchorPosition.TOPLEFT);
        var nr = M.text ? textRect(M.layer) : rectOf(M.layer.bounds);
        var tx = Math.round(nx0 + (M.r.l - ux0) * s), ty = Math.round(ny0 + (M.r.t - uy0) * s);
        M.layer.translate(new UnitValue(tx - nr.l, "px"), new UnitValue(ty - nr.t, "px"));
    }

    // 集計期間（第6章）
    var mn = null, mx = null;
    for (i = 0; i < keepDates.length; i++) {
        var q = keepDates[i].p;
        if (!mn || q.date < mn.date) mn = q;
        if (!mx || q.date > mx.date) mx = q;
    }
    if (period && mn) {
        var np = "集計期間：" + mn.y + "年" + mn.mo + "月" + mn.d + "日～" + mx.y + "年" + mx.mo + "月" + mx.d + "日";
        if (period.textItem.contents == np) log("  集計期間：変更なし");
        else {
            var pr = textRect(period);
            period.textItem.contents = np;
            var pr2 = textRect(period);
            period.translate(new UnitValue(pr.r - pr2.r, "px"), new UnitValue(pr.t - pr2.t, "px"));   // 右端をそろえる
            log("  集計期間：→ " + np);
        }
    }

    // 帯・日付・集計期間以外のレイヤーが動いていないか
    var moved = 0;
    for (i = 0; i < before.length; i++) {
        var B = before[i], skip = (B.layer == period);
        for (c = 0; c < removed.length && !skip; c++) if (removed[c] == B.layer) skip = true;
        for (c = 0; c < moveList.length && !skip; c++) if (moveList[c].layer == B.layer) skip = true;
        if (skip) continue;
        var br = rectOf(B.layer.bounds);
        if (br.l != B.r.l || br.t != B.r.t || br.r != B.r.r || br.b != B.r.b) { moved++; log("  ！位置が変わったレイヤー：" + B.layer.name); }
    }
    if (moved) throw new Error("ABORT: 帯・日付以外のレイヤーが動いたため保存しません（" + moved + "件）");
    log("  帯・日付以外のレイヤーの位置：変化なし");
    log("  残した帯 " + keepCards.length + " 枚・日付 " + keepDates.length + " 件");

    // 保存（第1-2節）
    checkActive(file.name);
    var so = new PhotoshopSaveOptions(); so.layers = true; so.embedColorProfile = true;
    doc.saveAs(outPsd, so, false, Extension.LOWERCASE);
    checkActive(outPsd.name);
    var jo = new JPEGSaveOptions(); jo.quality = CFG.JPEG_QUALITY; jo.embedColorProfile = true;
    jo.formatOptions = FormatOptions.STANDARDBASELINE; jo.matte = MatteType.NONE;
    doc.saveAs(outJpg, jo, true, Extension.LOWERCASE);
    log("  保存：" + outPsd.name + " / " + outJpg.name + "（元ファイルは変更なし）");
    closeAll();
}

function main() {
    var file = File.openDialog("帯の枚数を減らすPSDを選んでください", "*.psd");
    if (!file) return;
    var ans = prompt("残す帯の枚数", String(CFG.COUNT));
    if (ans === null) return;
    var count = parseInt(ans, 10);
    if (!(count > 0)) { alert("枚数が正しくありません"); return; }
    if (app.documents.length && !confirm("開いているドキュメントをすべて閉じてから作業します（未保存のものは保存するか聞かれます）。よろしいですか？")) return;
    var oldRuler = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;
    try { run(file, count); }
    catch (e) { log("エラー：" + e.message + (e.line ? "（" + e.line + "行目）" : "")); }
    finally {
        app.preferences.rulerUnits = oldRuler;
        var lf = new File(file.parent + "/cards_log(" + TODAY + ").txt");
        lf.encoding = "UTF-8"; lf.open("w"); lf.write(LOG.join("\n")); lf.close();
        alert(LOG.join("\n"));
    }
}
main();
