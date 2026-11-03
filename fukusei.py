#!/usr/bin/env python3
"""層の記録（sou.py の pNNN.json）から、同じ作りのページを Google スライドに作る（完コピの作り直し）。

手本そのものには触らない。作るのは別の新しい資料（サービスアカウントが成り代わる人のマイドライブ）だけ。

使い方
  python3 fukusei.py new <資料名>                                   新しい資料を作り、SLIDE_SHARE_TO に編集権限（通知メールなし）→ presId を出す
  python3 fukusei.py build <presId> <sou フォルダ> <media フォルダ> <ページ番号 ...> [--group] [--keep]
        ページを1枚ずつ後ろに足す（--keep なしなら最初に中身を全部消す）。番号の順に並ぶ
        --group … 手本の「束ね（グループ）」も作り直す（編集したときの層の扱いを同じにする）
  python3 fukusei.py dry <sou フォルダ> <media フォルダ> <ページ番号>   作らずに、要る素材と依頼の数だけ出す

作り方（層ごと・下から順に）
  pic / blip（画像・画像で塗った四角）… 元の画像を、切り抜き・透明度・縦横比を焼き込んだ PNG にして置く
  vec（自由な形）………………………… パス（直線と曲線）を単色かグラデーションで塗った PNG を作って置く（Slides API では自由な形を作れないため）
  shape（四角など）……………………… 同じ形・同じ塗り・同じ枠で作る
  text（文字）……………………………… 塗りは下に別の形で、文字は透明の文字の箱で。字・大きさ・色・太さ・行間・揃えを run ごとに写す
                                        箱の余白は Google スライドの既定 7.2pt。手本の余白（多くは 0）との差だけ箱を広げて文字の位置を合わせる
  line / video ……………………………… 同じ線・同じ動画
置き方は、手本の変形（回転・反転・ずれ）をそのまま使う。大きさだけを1倍にそろえる（画像の縦横比を正しく焼くため）
"""
import json, os, sys, math, hashlib, time
from PIL import Image, ImageDraw

D = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(D, 'assets', 'fukusei_cache')
# 筋（SLIDE_SUJI）：同時に2本回すときは筋ごとに一時置き場・控え・鍵を分ける（空なら今までと同じ）
SUJI = os.environ.get('SLIDE_SUJI', '')
EMU = 12700.0
PAD = 7.2
PX_PER_PT = 3.0
MAXPX = 3000


def services():
    from googleapiclient.discovery import build
    from settei import creds
    c = creds(['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations'])
    return build('drive', 'v3', credentials=c, cache_discovery=False), build('slides', 'v1', credentials=c, cache_discovery=False)


# ---------- 置き方 ----------
def norm(L):
    """大きさを1倍にそろえる：size=(描かれる幅, 高さ)pt、変形=回転・反転・ずれだけ"""
    a, b, tx, c, d, ty = L['m']
    sx, sy = math.hypot(a, c), math.hypot(b, d)
    w, h = L['w'] * sx, L['h'] * sy
    if sx == 0 or sy == 0:
        return max(w, 0.01), max(h, 0.01), [1, 0, tx, 0, 1, ty]
    return w, h, [a / sx, b / sy, tx, c / sx, d / sy, ty]


# 文字の箱だけを右・下へずらす量（pt）。手本との画素のずれを測って決める（kekka.md の実験3）
TEXT_DX = float(os.environ.get('FUKUSEI_TEXT_DX', '0'))
TEXT_DY = float(os.environ.get('FUKUSEI_TEXT_DY', '0'))
# 文字の箱の幅を狭める量（pt）。0 で前の形に戻る（11/02 p463 の折り返しの実験）
SEMA = float(os.environ.get('FUKUSEI_SEMA', '0.9'))

def grow(w, h, m, d):
    """箱を四方に d pt 広げる（回転していても中身の位置がずれないように左上をずらす）"""
    if not d:
        return w, h, m
    return w + 2 * d, h + 2 * d, [m[0], m[1], m[2] - (m[0] * d + m[1] * d), m[3], m[4], m[5] - (m[3] * d + m[4] * d)]


def ep(page, w, h, m):
    return {'pageObjectId': page, 'size': {'width': {'magnitude': max(w, 0.01) * EMU, 'unit': 'EMU'}, 'height': {'magnitude': max(h, 0.01) * EMU, 'unit': 'EMU'}},
            'transform': {'scaleX': m[0], 'shearX': m[1], 'translateX': m[2] * EMU, 'shearY': m[3], 'scaleY': m[4], 'translateY': m[5] * EMU, 'unit': 'EMU'}}


def rgbc(hx):
    hx = (hx or '#000000').lstrip('#')
    return {'red': int(hx[0:2], 16) / 255, 'green': int(hx[2:4], 16) / 255, 'blue': int(hx[4:6], 16) / 255}


# ---------- 素材を焼く ----------
def save_png(im, tag):
    os.makedirs(CACHE, exist_ok=True)
    import io
    bio = io.BytesIO()
    im.save(bio, 'PNG', optimize=False)
    h = hashlib.md5(bio.getvalue()).hexdigest()
    f = os.path.join(CACHE, f'{h}.png')
    if not os.path.exists(f):
        open(f, 'wb').write(bio.getvalue())
    return f


def open_media(path):
    """素材の画像を開く。PIL が読めない JPEG（PPTX 書き出しの image78.jpg「Invalid component ID 0 in SOS」・11/01 p60）は
    macOS の sips で PNG に直してから開く（sips は読める・Google の表示とも同じ絵）"""
    try:
        return Image.open(path).convert('RGBA')
    except OSError:
        import subprocess
        out = os.path.join(CACHE, 'sips-' + hashlib.md5(open(path, 'rb').read()).hexdigest() + '.png')
        if not os.path.exists(out):
            subprocess.run(['sips', '-s', 'format', 'png', path, '--out', out], check=True, capture_output=True)
        return Image.open(out).convert('RGBA')


def bake_blip(fill, media_dir, w, h):
    """画像：切り抜き（srcRect）→ 箱の縦横比に合わせる → 透明度を掛ける"""
    im = open_media(os.path.join(media_dir, fill['media']))
    src = fill.get('src')
    if src:
        W0, H0 = im.size
        l, t, r, b = (src.get(k, 0) for k in 'ltrb')
        box = (l * W0, t * H0, W0 - r * W0, H0 - b * H0)
        # はみ出し（負の値）は透明で足す
        nw, nh = max(1, round(box[2] - box[0])), max(1, round(box[3] - box[1]))
        can = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
        crop = im.crop((max(0, round(box[0])), max(0, round(box[1])), min(W0, round(box[2])), min(H0, round(box[3]))))
        can.paste(crop, (max(0, -round(box[0])), max(0, -round(box[1]))))
        im = can
    fr = fill.get('fillRect')
    W0, H0 = im.size
    want = w / h if h else 1
    if fr:
        # fillRect：箱の中で画像を置く範囲（内側への余白・負は箱の外へはみ出して切れる）
        l, t, r, b = (fr.get(k, 0) for k in 'ltrb')
        fw, fh = max(1e-6, 1 - l - r), max(1e-6, 1 - t - b)
        k = max(W0 / (fw * max(w, 1e-6)), H0 / (fh * max(h, 1e-6)))
        k = min(k, MAXPX / max(w, h, 1))
        cw, ch = max(1, round(w * k)), max(1, round(h * k))
        tw, th = max(1, round(cw * fw)), max(1, round(ch * fh))
        can = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        rs = im.resize((tw, th), Image.LANCZOS)
        # 空の透明キャンバスへは mask なしで貼る（絵自身を mask にすると半透明が二乗になり薄くなる・p354 で実測 11/02）
        can.paste(rs, (round(cw * l), round(ch * t)))
        im = can
    elif abs((W0 / H0) - want) / want > 0.004:
        tw = max(W0, 2)
        th = max(1, round(tw / want))
        if th > MAXPX:
            th = MAXPX
            tw = max(1, round(th * want))
        im = im.resize((tw, th), Image.LANCZOS)
    al = fill.get('alpha', 1.0)
    if al < 0.999:
        a = im.getchannel('A').point(lambda v: int(v * al))
        im.putalpha(a)
    return save_png(im, 'blip')


def bez(p0, p1, p2, p3, n=20):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def subpaths(path, sx, sy):
    polys, cur = [], []
    pos = (0, 0)
    for op, pts in path['cmds']:
        P = [(x * sx, y * sy) for x, y in pts]
        if op == 'moveTo':
            if len(cur) > 2:
                polys.append(cur)
            cur = [P[0]]
            pos = P[0]
        elif op == 'lnTo':
            cur.append(P[0])
            pos = P[0]
        elif op == 'cubicBezTo':
            cur += bez(pos, P[0], P[1], P[2])
            pos = P[2]
        elif op == 'quadBezTo':
            q = P
            c1 = (pos[0] + 2 / 3 * (q[0][0] - pos[0]), pos[1] + 2 / 3 * (q[0][1] - pos[1]))
            c2 = (q[1][0] + 2 / 3 * (q[0][0] - q[1][0]), q[1][1] + 2 / 3 * (q[0][1] - q[1][1]))
            cur += bez(pos, c1, c2, q[1])
            pos = q[1]
        elif op == 'close':
            if len(cur) > 2:
                polys.append(cur)
            cur = []
    if len(cur) > 2:
        polys.append(cur)
    return polys


def grad_img(fill, W, H):
    import numpy as np
    stops = sorted(fill['stops'], key=lambda s: s['pos'])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    if fill.get('path') in ('circle', 'rect', 'shape'):
        fr = fill.get('fillToRect') or {'l': .5, 't': .5, 'r': .5, 'b': .5}
        cx, cy = fr['l'] * W, fr['t'] * H
        dist = np.hypot((xx - cx) / max(W, 1), (yy - cy) / max(H, 1))
        corners = [math.hypot((x - cx) / W, (y - cy) / H) for x, y in ((0, 0), (W, 0), (0, H), (W, H))]
        t = dist / max(corners)
    else:
        ang = math.radians(fill.get('angle', 0))
        dx, dy = math.cos(ang), math.sin(ang)
        p = xx * dx + yy * dy
        cs = [x * dx + y * dy for x, y in ((0, 0), (W, 0), (0, H), (W, H))]
        t = (p - min(cs)) / max(1e-6, (max(cs) - min(cs)))
    t = np.clip(t, 0, 1)
    out = np.zeros((H, W, 4), np.float32)
    P = [s['pos'] for s in stops]
    C = [list(int(s['color'][i:i + 2], 16) for i in (1, 3, 5)) + [s['alpha'] * 255] for s in stops]
    for ch in range(4):
        out[..., ch] = np.interp(t, P, [c[ch] for c in C])
    return Image.fromarray(out.astype('uint8'), 'RGBA')


def vec_pad(L):
    """枠線は形の線の上に半分ずつ乗るので、外側に出る半分ぶん絵を広げる（pt）"""
    ol = L.get('outline')
    return (ol['w'] / 2.0 + 0.5) if ol else 0.0


def bake_vec(L, w, h):
    """自由な形 → PNG（4倍で描いて縮める・穴は偶奇で抜く）。枠線の外側半分ぶん周りを広げて描く"""
    pad = vec_pad(L)
    k = min(PX_PER_PT, MAXPX / max(w + 2 * pad, h + 2 * pad, 1))
    W, H = max(1, round((w + 2 * pad) * k)), max(1, round((h + 2 * pad) * k))
    S = 4
    ox, oy = pad * k * S, pad * k * S
    mask = Image.new('L', (W * S, H * S), 0)
    stroke = None
    fill = L['fill']
    for path in L['path']:
        pw, ph = path['w'] or L['w'] * EMU, path['h'] or L['h'] * EMU
        sx, sy = (w * k * S) / pw, (h * k * S) / ph
        polys = [[(x + ox, y + oy) for x, y in poly] for poly in subpaths(path, sx, sy)]
        if path.get('fill') != 'none':
            for poly in polys:
                m2 = Image.new('L', mask.size, 0)
                ImageDraw.Draw(m2).polygon(poly, fill=255)
                from PIL import ImageChops
                mask = ImageChops.logical_xor(mask.convert('1'), m2.convert('1')).convert('L')
        ol = L.get('outline')
        if ol and path.get('stroke') != '0':
            stroke = stroke or Image.new('L', mask.size, 0)
            dr = ImageDraw.Draw(stroke)
            lw = max(1, round(ol['w'] * k * S))
            for poly in polys:
                dr.line(poly + [poly[0]], fill=255, width=lw, joint='curve')
    mask = mask.resize((W, H), Image.LANCZOS)
    if fill['type'] == 'solid':
        r, g, b = (int(fill['color'][i:i + 2], 16) for i in (1, 3, 5))
        im = Image.new('RGBA', (W, H), (r, g, b, 255))
        a = mask.point(lambda v: int(v * fill.get('alpha', 1.0)))
        im.putalpha(a)
    else:
        im = grad_img(fill, W, H)
        from PIL import ImageChops
        im.putalpha(ImageChops.multiply(im.getchannel('A'), mask))
    if stroke is not None:
        ol = L['outline']
        r, g, b = (int(ol['color'][i:i + 2], 16) for i in (1, 3, 5))
        st = Image.new('RGBA', (W, H), (r, g, b, 0))
        st.putalpha(stroke.resize((W, H), Image.LANCZOS).point(lambda v: int(v * ol.get('alpha', 1.0))))
        im = Image.alpha_composite(im, st)
    return save_png(im, 'vec')


# ---------- 依頼を組む ----------
TEXT_FIELDS = {}


def glyph_ire(tx):
    """手本の記号（• など）を文字として段落の頭に入れる。Slides の箇条書きの型には手本と同じ記号が無い（BULLET_DISC は ●）。
    手本の描き方（p30・p44 を画像で実測）：本文は indentStart（＝indentFirstLine＋記号の幅 w）から、記号は indentFirstLine−w から。
    → 字下げの頭を w 左へずらし、記号＋すき間（en スペース 0.5em を 0.7 倍の大きさ＝w）を文字で入れる（行の高さは本文の字で決まるので変わらない）"""
    W = 0.35   # Arial の • の幅（em）
    if not any(p.get('glyph') for p in tx['paras']):
        return tx
    ins = sorted(p['start'] for p in tx['paras'] if p.get('glyph'))
    sh = lambda i, incl: i + 2 * sum(1 for x in ins if x < i or (incl and x == i))
    runs = [dict(r, start=sh(r['start'], True), end=sh(r['end'], False)) for r in tx['runs']]
    paras = []
    for p in tx['paras']:
        q = dict(p, start=sh(p['start'], False), end=sh(p['end'], False))
        if p.get('glyph'):
            q['bullet'] = False
            gs = p['glyph_style']
            w = W * (gs['size'] or 0)
            q['indentFirstLine'] = max(0.0, (p.get('indentFirstLine') or 0) - w)
            runs.append({'start': q['start'], 'end': q['start'] + 1, 'text': p['glyph'], 'font': gs['font'], 'weight': gs['weight'],
                         'size': gs['size'], 'color': gs['color'], 'bold': gs['bold']})
            runs.append({'start': q['start'] + 1, 'end': q['start'] + 2, 'text': '\u2002', 'font': gs['font'], 'weight': gs['weight'],
                         'size': round(2 * W * (gs['size'] or 0), 2), 'color': gs['color'], 'bold': gs['bold']})
        paras.append(q)
    c = tx['content']
    for x in reversed(ins):
        c = c[:x] + [p['glyph'] for p in tx['paras'] if p['start'] == x][0] + '\u2002' + c[x:]
    return dict(tx, content=c, runs=sorted(runs, key=lambda r: r['start']), paras=paras)


def gyou_furiwake(tx):
    """行の送りを手本にそろえる。Slides は新しく作った文字の行の高さ（字の大きさ×1.2×行間％）を 1px（0.75pt）に丸める。
    手本（PPTX から来た文字）は丸められないので、下の行ほど上下にずれていた（p168 は1行 50.53px→51px で7行目が6px下・p51 は 38.4→38px）。
    段落の空き（spaceAbove）も 1px に丸められて効かなかった（11/02 実測）→ 段落ごとの行間を切り下げ・切り上げの px に振り分け、
    積み上げた位置が手本から 0.5px 以内に収まるようにする（p168 違う所 7.0%→1.93%）"""
    acc_t, acc_r, paras = 0.0, 0, []
    for p in tx['paras']:
        q = dict(p)
        sz = max([r.get('size') or 0 for r in tx['runs'] if r['start'] < p['end'] and r['end'] > p['start']] or [0])
        ls = p.get('lineSpacing') or 100
        if '\u000b' in tx['content'][p['start']:p['end']]:
            # 改行記号（\v）で行が分かれる段落は、行ごとに字の大きさが違い1つの行間では振り分けられない。
            # 段落の最後の改行の大きさ（p319 は 35pt）まで数えて下へずれた（11/02 実測：手本どおりの行間 130.03 で上下の差 0）→ 手本の行間のまま
            if sz:
                t = sz * 1.2 * ls / 100 / 0.75
                acc_t += t
                acc_r += t
            paras.append(q)
            continue
        if sz:
            t = sz * 1.2 * ls / 100 / 0.75
            acc_t += t
            h = round(acc_t) - acc_r
            acc_r += h
            if h > 0:
                q['lineSpacing'] = ls * h / t
        paras.append(q)
    return dict(tx, paras=paras)


def text_reqs(oid, tx):
    R = []
    tx = gyou_furiwake(glyph_ire(tx))
    body = tx['content']
    if body.endswith('\n'):
        body = body[:-1]
    if not body:
        return R
    R.append({'insertText': {'objectId': oid, 'insertionIndex': 0, 'text': body}})
    n = len(body)
    for r in tx['runs']:
        s, e = r['start'], min(r['end'], n)
        if e <= s:
            continue
        st, f = {}, []
        if r.get('font'):
            st['weightedFontFamily'] = {'fontFamily': r['font'], 'weight': r.get('weight') or 400}
            f.append('weightedFontFamily')
        if r.get('size'):
            st['fontSize'] = {'magnitude': r['size'], 'unit': 'PT'}
            f.append('fontSize')
        if r.get('color'):
            st['foregroundColor'] = {'opaqueColor': {'rgbColor': rgbc(r['color'])}}
            f.append('foregroundColor')
        if r.get('bg'):
            st['backgroundColor'] = {'opaqueColor': {'rgbColor': rgbc(r['bg'])}}
            f.append('backgroundColor')
        for k, kk in (('bold', 'bold'), ('italic', 'italic'), ('underline', 'underline'), ('strike', 'strikethrough')):
            st[kk] = bool(r.get(k))
            f.append(kk)
        if r.get('baseline') and r['baseline'] != 'NONE':
            st['baselineOffset'] = r['baseline']
            f.append('baselineOffset')
        if r.get('link'):
            st['link'] = r['link']
            f.append('link')
        R.append({'updateTextStyle': {'objectId': oid, 'textRange': {'type': 'FIXED_RANGE', 'startIndex': s, 'endIndex': e}, 'style': st, 'fields': ','.join(f)}})
    for p in tx['paras']:
        s, e = p['start'], min(p['end'], n)
        if e <= s:
            e = s
        st, f = {}, []
        if p.get('align'):
            st['alignment'] = p['align']
            f.append('alignment')
        if p.get('lineSpacing'):
            st['lineSpacing'] = p['lineSpacing']
            f.append('lineSpacing')
        for k in ('spaceAbove', 'spaceBelow', 'indentStart', 'indentEnd', 'indentFirstLine'):
            st[k] = {'magnitude': p.get(k) or 0, 'unit': 'PT'}
            f.append(k)
        if p.get('spacingMode'):
            st['spacingMode'] = p['spacingMode']
            f.append('spacingMode')
        if s >= n and body.endswith('\n'):
            # 最後の空の段落。n−1 から当てると一つ前の段落の揃えを上書きする（p36 の中央揃えが左揃えになった・11/02）
            continue
        rng = {'type': 'FIXED_RANGE', 'startIndex': s, 'endIndex': max(e, s + 1) if s < n else n} if s < n else {'type': 'FROM_START_INDEX', 'startIndex': max(0, n - 1)}
        R.append({'updateParagraphStyle': {'objectId': oid, 'textRange': rng, 'style': st, 'fields': ','.join(f)}})
        if p.get('bullet') and s < n:
            R.append({'createParagraphBullets': {'objectId': oid, 'textRange': rng, 'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'}})
    return R


def page_reqs(pg, page_oid, media_dir, U, with_group=False):
    """1ページの依頼。U は 焼いた PNG のパス → 公開URL（dry のときは偽物）"""
    R = []
    made = {}          # 手本の id → 作った id（束ねに使う）
    bg = pg.get('bg')
    if bg:
        if bg['type'] == 'solid':
            R.append({'updatePageProperties': {'objectId': page_oid, 'pageProperties': {'pageBackgroundFill': {'solidFill': {'color': {'rgbColor': rgbc(bg['color'])}, 'alpha': bg.get('alpha', 1.0)}}}, 'fields': 'pageBackgroundFill.solidFill'}})
        elif bg['type'] == 'blip' and bg.get('media'):
            f = bake_blip({'media': bg['media']}, media_dir, 720, 405)
            R.append({'updatePageProperties': {'objectId': page_oid, 'pageProperties': {'pageBackgroundFill': {'stretchedPictureFill': {'contentUrl': U[f]}}}, 'fields': 'pageBackgroundFill.stretchedPictureFill.contentUrl'}})
    n = 0
    for L in pg['layers']:
        kind = L['kind']
        if kind == 'group':
            continue
        w, h, m = norm(L)
        oid = f'{page_oid}_{L["z"]}'
        if kind in ('pic', 'blip') and L.get('fill', {}).get('media'):
            f = bake_blip(L['fill'], media_dir, w, h)
            R.append({'createImage': {'objectId': oid, 'url': U[f], 'elementProperties': ep(page_oid, w, h, m)}})
            made[L['id']] = [oid]
        elif kind == 'vec':
            f = bake_vec(L, w, h)
            R.append({'createImage': {'objectId': oid, 'url': U[f], 'elementProperties': ep(page_oid, *grow(w, h, m, vec_pad(L)))}})
            made[L['id']] = [oid]
        elif kind in ('shape', 'text'):
            ids = []
            fl = L.get('fill')
            if fl or L.get('outline'):
                if L.get('path') and fl and fl['type'] in ('solid', 'grad'):
                    f = bake_vec(L, w, h)
                    R.append({'createImage': {'objectId': oid + 'f', 'url': U[f], 'elementProperties': ep(page_oid, *grow(w, h, m, vec_pad(L)))}})
                else:
                    st = L.get('shapeType') if L.get('shapeType') not in (None, 'TEXT_BOX', 'CUSTOM') else 'RECTANGLE'
                    R.append({'createShape': {'objectId': oid + 'f', 'shapeType': st, 'elementProperties': ep(page_oid, w, h, m)}})
                    sp, fs = {}, []
                    if fl and fl['type'] == 'solid':
                        sp['shapeBackgroundFill'] = {'solidFill': {'color': {'rgbColor': rgbc(fl['color'])}, 'alpha': fl.get('alpha', 1.0)}}
                        fs.append('shapeBackgroundFill.solidFill')
                    else:
                        sp['shapeBackgroundFill'] = {'propertyState': 'NOT_RENDERED'}
                        fs.append('shapeBackgroundFill.propertyState')
                    ol = L.get('outline')
                    if ol:
                        sp['outline'] = {'outlineFill': {'solidFill': {'color': {'rgbColor': rgbc(ol['color'])}, 'alpha': ol.get('alpha', 1.0)}},
                                         'weight': {'magnitude': ol['w'], 'unit': 'PT'}, 'dashStyle': ol.get('dash') or 'SOLID'}
                        fs += ['outline.outlineFill.solidFill', 'outline.weight', 'outline.dashStyle']
                    else:
                        sp['outline'] = {'propertyState': 'NOT_RENDERED'}
                        fs.append('outline.propertyState')
                    R.append({'updateShapeProperties': {'objectId': oid + 'f', 'shapeProperties': sp, 'fields': ','.join(fs)}})
                ids.append(oid + 'f')
            if L.get('text'):
                ins = L.get('inset') or {'l': 0, 'r': 0, 't': 0, 'b': 0}
                dl, dr_, dt, db = PAD - ins['l'], PAD - ins['r'], PAD - ins['t'], PAD - ins['b']
                # 箱を広げた分だけ、箱の左上を（回転を考えて）ずらす
                tx = m[2] - (m[0] * dl + m[1] * dt)
                ty = m[5] - (m[3] * dl + m[4] * dt)
                tw, th = w + dl + dr_, h + dt + db
                if L.get('wrap') == 'none':
                    extra = max(20.0, tw * 0.3)
                    al = (L['text']['paras'][0].get('align') if L['text']['paras'] else None) or 'START'
                    if al == 'CENTER':
                        tx -= m[0] * extra / 2
                        ty -= m[3] * extra / 2
                    elif al == 'END':
                        tx -= m[0] * extra
                        ty -= m[3] * extra
                    tw += extra
                # 縦位置のずれ（20ページ・84箱の実測 kekka.md 実験3）：手本は最後の行の行間の伸び
                # （大きさ×1.2×(行間-100%)）を数えない → 下寄せは全部・中央寄せは半分だけ下へ。
                # 上寄せで行間の伸びが4pt以上は 0.45pt 下（1600px で1画素・84箱中71箱がこの向き）
                if L['text']['paras']:
                    lsp = (L['text']['paras'][-1].get('lineSpacing') or 100) / 100.0
                    big = max([r.get('size') or 0 for r in L['text']['runs'] if r['text'].strip()] or [0])
                    anc = L.get('contentAlignment') or 'TOP'
                    d = 0.0
                    if lsp > 1 and anc == 'BOTTOM':
                        d = big * 1.2 * (lsp - 1)
                    elif lsp > 1 and anc == 'MIDDLE':
                        d = big * 1.2 * (lsp - 1) / 2
                    elif anc == 'TOP' and big * 1.2 * (lsp - 1) >= 4.0:
                        d = 0.45                      # 行間の伸びが4pt以上（p27 24pt×115%=4.3 は下げる／p4 16〜20pt×115% は下げない）
                    tx += m[1] * d
                    ty += m[4] * d
                    # 左右のずれ（33枚・104箱の実測 kekka.md 実験4）：左揃えは 0.45pt 右（36箱中34）・右揃えは 0.45pt 左・中央はそのまま
                    al0 = (L['text']['paras'][0].get('align') or 'START')
                    # 余白を広げた箱（元の余白が 7.2pt 未満）だけ。元から 7.2pt の箱（p4）はずらすと悪くなる（0.61→1.71%）
                    hx = {'START': 0.45, 'JUSTIFIED': 0.45, 'END': -0.45}.get(al0, 0.0) if dl > 0.01 else 0.0
                    tx += m[0] * hx
                    ty += m[3] * hx
                    # 幅（11/02 p463 の実験）：作り直しは同じ箱で約0.9pt広く並べる（実の余白は約6.75pt）
                    # → 余白を広げた箱だけ、文字の位置を変えずに幅を SEMA pt 狭める（手本と同じ所で折り返す）
                    if dl > 0.01 and L.get('wrap') != 'none' and SEMA:
                        sx_ = {'START': 0.0, 'JUSTIFIED': 0.0, 'END': SEMA}.get(al0, SEMA / 2)
                        tx += m[0] * sx_
                        ty += m[3] * sx_
                        tw -= SEMA
                tx += TEXT_DX
                ty += TEXT_DY
                mm = [m[0], m[1], tx, m[3], m[4], ty]
                R.append({'createShape': {'objectId': oid + 't', 'shapeType': 'TEXT_BOX', 'elementProperties': ep(page_oid, tw, th, mm)}})
                if L.get('contentAlignment'):
                    R.append({'updateShapeProperties': {'objectId': oid + 't', 'shapeProperties': {'contentAlignment': L['contentAlignment']}, 'fields': 'contentAlignment'}})
                R += text_reqs(oid + 't', L['text'])
                ids.append(oid + 't')
            if ids:
                made[L['id']] = ids
        elif kind == 'line':
            ln = L['line']
            R.append({'createLine': {'objectId': oid, 'category': 'STRAIGHT', 'elementProperties': ep(page_oid, w, h, m)}})
            lp, fs = {'weight': {'magnitude': ln['weight'] or 1, 'unit': 'PT'}}, ['weight']
            if ln.get('color'):
                lp['lineFill'] = {'solidFill': {'color': {'rgbColor': rgbc(ln['color'])}, 'alpha': ln.get('alpha', 1.0)}}
                fs.append('lineFill.solidFill')
            for k in ('dash', 'start', 'end'):
                if ln.get(k):
                    lp[{'dash': 'dashStyle', 'start': 'startArrow', 'end': 'endArrow'}[k]] = ln[k]
                    fs.append({'dash': 'dashStyle', 'start': 'startArrow', 'end': 'endArrow'}[k])
            R.append({'updateLineProperties': {'objectId': oid, 'lineProperties': lp, 'fields': ','.join(fs)}})
            made[L['id']] = [oid]
        elif kind == 'video' and L['video'].get('id'):
            R.append({'createVideo': {'objectId': oid, 'source': L['video']['source'], 'id': L['video']['id'], 'elementProperties': ep(page_oid, w, h, m)}})
            made[L['id']] = [oid]
        n += 1
    if with_group:
        groups = sorted([L for L in pg['layers'] if L['kind'] == 'group'], key=lambda L: -L['depth'])
        for G in groups:
            kids = [i for c in G['children'] for i in made.get(c, [])]
            if len(kids) >= 2:
                gid = f'{page_oid}_g{G["z"]}'
                R.append({'groupObjects': {'groupObjectId': gid, 'childrenObjectIds': kids}})
                made[G['id']] = [gid]
            elif kids:
                made[G['id']] = kids
    return R


def needed_files(pg, media_dir):
    class Rec(dict):
        def __missing__(self, k):
            self[k] = 'x://' + k
            return self[k]
    U = Rec()
    page_reqs(pg, 'dry', media_dir, U)
    return list(U.keys())


# ---------- 上げる・作る ----------
def tmp_folder(drv):
    nm = '作り直し素材（一時）' + SUJI
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
    r = drv.files().list(q=q, fields='files(id)').execute()['files']
    if r:
        return r[0]['id']
    return drv.files().create(body={'name': nm, 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute()['id']


def upload(drv, folder, files):
    from googleapiclient.http import MediaFileUpload
    cf = os.path.join(CACHE, f'drive_ids{SUJI}.json')
    cache = json.load(open(cf)) if os.path.exists(cf) else {}
    ids = {}
    for f in files:
        k = os.path.basename(f)
        if k in cache and cache[k].get('folder') == folder:
            ids[f] = cache[k]['id']
            continue
        fid = drv.files().create(body={'name': k, 'parents': [folder]}, media_body=MediaFileUpload(f, mimetype='image/png', resumable=False), fields='id').execute()['id']
        cache[k] = {'id': fid, 'folder': folder}
        ids[f] = fid
        json.dump(cache, open(cf, 'w'))
    return ids


def public_on(drv, folder):
    return drv.permissions().create(fileId=folder, body={'type': 'anyone', 'role': 'reader'}, fields='id').execute()['id']


def public_off(drv, folder, ids):
    """フォルダの公開を外す → 中のファイル（引き継ぎで公開になっていた）も外れたかを1つずつ数える"""
    for p in drv.permissions().list(fileId=folder, fields='permissions(id,type)').execute()['permissions']:
        if p['type'] in ('anyone', 'domain'):
            drv.permissions().delete(fileId=folder, permissionId=p['id']).execute()
    # 引き継ぎで付いていた公開は、フォルダから外したあと少し遅れて消える（2026-11-01 実測：直後 2 件→数十秒後 0 件）
    for t in range(8):
        left = 0
        for fid in [folder] + list(ids):
            ps = drv.permissions().list(fileId=fid, fields='permissions(id,type)').execute()['permissions']
            for p in ps:
                if p['type'] in ('anyone', 'domain'):
                    left += 1
                    try:
                        drv.permissions().delete(fileId=fid, permissionId=p['id']).execute()
                    except Exception:
                        pass
        if left == 0:
            return 0
        time.sleep(10)
    return left


def wait_public(urls, limit=240):
    import subprocess, concurrent.futures as cf
    def ok(u):
        r = subprocess.run(['curl', '-s', '-L', '-o', '/dev/null', '-w', '%{http_code} %{content_type}', u], capture_output=True, text=True).stdout
        return r.startswith('200') and 'image' in r
    t0, rest = time.time(), list(urls)
    while rest and time.time() - t0 < limit:
        with cf.ThreadPoolExecutor(8) as ex:
            res = list(ex.map(ok, rest))
        rest = [u for u, g in zip(rest, res) if not g]
        if rest:
            time.sleep(8)
    return len(urls) - len(rest), len(urls)


def cmd_new(title):
    drv, sl = services()
    p = sl.presentations().create(body={'title': title}).execute()
    pid = p['presentationId']
    from settei import SHARE_TO
    if SHARE_TO:
        drv.permissions().create(fileId=pid, body={'type': 'user', 'role': 'writer', 'emailAddress': SHARE_TO}, sendNotificationEmail=False).execute()
    print(json.dumps({'presentation': pid, 'url': f'https://docs.google.com/presentation/d/{pid}/edit'}, ensure_ascii=False))


def cmd_build(pid, sou, media, pages, with_group=False, keep=False):
    # 一時置き場のフォルダは1つを使い回すので、作る処理は同時に1本だけ（11/01 試しの作り直しが周回の公開を途中で外し、周回の画像が取れなくなった）
    import fcntl
    lock = open(os.path.join(CACHE, f'build{SUJI}.lock'), 'w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    drv, sl = services()
    pgs = [json.load(open(os.path.join(sou, f'p{n:03d}.json'))) for n in pages]
    files = sorted({f for pg in pgs for f in needed_files(pg, media)})
    folder = tmp_folder(drv)
    ids = upload(drv, folder, files)
    U = {f: f'https://drive.google.com/uc?export=download&id={i}' for f, i in ids.items()}
    perm = None
    try:
        public_on(drv, folder)
        got, tot = wait_public(list(U.values()))
        print(f'公開の確認 {got}/{tot}')
        cur = sl.presentations().get(presentationId=pid, fields='slides.objectId').execute().get('slides', [])
        # 仮のページの名前は毎回変える（前の回が途中で落ちると tmp_blank が残り、同じ名前では作れない）
        blank = f'tmp_blank_{int(time.time() * 1000) % 10 ** 9}'
        if not keep and cur:
            sl.presentations().batchUpdate(presentationId=pid, body={'requests': [{'createSlide': {'objectId': blank, 'slideLayoutReference': {'predefinedLayout': 'BLANK'}}}] +
                                                                    [{'deleteObject': {'objectId': s['objectId']}} for s in cur]}).execute()
            cur = [{'objectId': blank}]
        out = []
        for n, pg in zip(pages, pgs):
            sid = f'k{n:03d}_{int(time.time()) % 100000}'
            reqs = [{'createSlide': {'objectId': sid, 'slideLayoutReference': {'predefinedLayout': 'BLANK'}}}]
            reqs += page_reqs(pg, sid, media, U, with_group)
            t0 = time.time()
            for i in range(0, len(reqs), 400):
                for t in range(4):
                    try:
                        sl.presentations().batchUpdate(presentationId=pid, body={'requests': reqs[i:i + 400]}).execute()
                        break
                    except Exception as e:
                        if t == 3:
                            raise
                        print('  やり直し', n, str(e)[:200])
                        time.sleep(10 * (t + 1))
            out.append({'page': n, 'slide': sid, 'reqs': len(reqs), 'sec': round(time.time() - t0, 1)})
            print(n, len(reqs), '依頼', out[-1]['sec'], '秒')
        if not keep:
            sl.presentations().batchUpdate(presentationId=pid, body={'requests': [{'deleteObject': {'objectId': blank}}]}).execute()
        print(json.dumps(out, ensure_ascii=False))
    finally:
        left = public_off(drv, folder, ids.values())
        print(f'公開の残り {left} 件')


def main():
    a = sys.argv[1:]
    if a[0] == 'new':
        cmd_new(a[1])
    elif a[0] == 'build':
        flags = [x for x in a if x.startswith('--')]
        a = [x for x in a if not x.startswith('--')]
        cmd_build(a[1], a[2], a[3], [int(x) for x in a[4:]], '--group' in flags, '--keep' in flags)
    elif a[0] == 'dry':
        pg = json.load(open(os.path.join(a[1], f'p{int(a[3]):03d}.json')))
        fs = needed_files(pg, a[2])
        class Rec(dict):
            def __missing__(self, k):
                return 'x://' + k
        R = page_reqs(pg, 'dry', a[2], Rec(), True)
        print(len(fs), '素材', len(R), '依頼')


if __name__ == '__main__':
    main()
