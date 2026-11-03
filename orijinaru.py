#!/usr/bin/env python3
"""型の目録だけを使って、手本に無い文言のページを作る（オリジナル作成）。

使い方  python3 orijinaru.py <作業フォルダ> <台本.json> <出す先>
  台本.json … [{"kata": "C 中央の一言＋下に人物", "moji": ["1つめの箱の文", "2つめ…"], "hito": "考える"}, ...]
     kata  … kata-index.json の型の名前（見本ページの層の作りをそのまま使う）。"base": 79 で手本のページを直に指してもよい
     moji  … 文字の箱へ上から順（同じ高さなら左から）に入れる。【】で囲んだ所は手本の強調色（赤など）になる。改行は \n
             箱が余ったら、その箱は消す（手本の文を残さない）
     hito  … 人物の絵を差し替える気持ち（make.py の HITO と同じ：考える 悩む 説明 成功 PC 挨拶 調べる AI 贈り物 グラフ）。無ければ手本の絵のまま
     icon  … 線画アイコンを読む順に差し替える（assets/icon/ の名前・例 ["chat","calendar_month"]）。手本の黒い線画と同じ #1A1A1A に塗る
             手本でその場所のまわりが暗い（紺の帯の上）ときは白・帯にまたがるときは手本の赤 #B4242C（tehon-img/ の手本の画像で見る）
     【】を字のまま出したいときは \\【 \\】 と書く
  出す先/sou/p9001.json … を作る → そのまま fukusei.py build <presId> <出す先>/sou <media> 9001 9002 … で作れる
"""
import json, os, sys, copy, math, re, zlib

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)


def lum(hx):
    r, g, b = (int(hx[i:i + 2], 16) for i in (1, 3, 5))
    return r, g, b


def is_accent(hx):
    if not hx:
        return False
    r, g, b = lum(hx)
    return r > 150 and r - b > 60 and r - g > 60


def order(layers):
    return sorted([L for L in layers if L['kind'] in ('text',) or (L['kind'] in ('shape', 'vec') and L.get('text'))],
                  key=lambda L: (round(L['box'][1] / 12), L['box'][0]))


def runs_from(s, base_run, accent):
    """「【強調】」を強調色に。改行で段落を分ける"""
    s = s.replace('\\【', '\x01').replace('\\】', '\x02')
    parts = re.split(r'(【[^】]*】)', s)
    runs, i = [], 0
    for p in parts:
        if not p:
            continue
        acc = p.startswith('【') and p.endswith('】')
        t = (p[1:-1] if acc else p).replace('\x01', '【').replace('\x02', '】')
        r = copy.deepcopy(base_run)
        r['text'] = t
        r['start'], r['end'] = i, i + len(t)
        if acc and accent:
            r['color'] = accent
        runs.append(r)
        i += len(t)
    return runs, i


def haba(t):
    """字の幅（全角＝1）。半角の英数・記号は0.5（11/03「STEP 1」を6字と数えて箱を2.5倍に伸ばした）"""
    return sum(0.5 if ord(c) < 0x2000 else 1 for c in t)


def need_h(text, w, s, ls):
    per = max(1, int(w / s))
    n = sum(max(1, math.ceil(haba(l) / per)) for l in text.split('\n'))
    return n * s * 1.45 * (ls / 100.0)


def fit_size(text, w, h, size, ls, grow=2.5):
    """先に箱を下へ伸ばし（元の高さの grow 倍まで）、それでも入らなければ字を小さくする。
    1字＝字の大きさの正方形・行の高さ＝大きさ×1.45×行間。返り値は（字の大きさ, 箱の高さ）"""
    s = size
    nh = need_h(text, w, s, ls)
    if nh > h * 1.35 + s:
        h = min(h * grow, nh)
    while s > 9 and need_h(text, w, s, ls) > h * 1.35 + s:
        s -= 0.5
    return s, h


def fill_text(L, s):
    tx = L['text']
    runs = [r for r in tx['runs'] if r['text'].strip()] or tx['runs']
    base = max(runs, key=lambda r: len(r['text']))
    base = copy.deepcopy(base)
    if is_accent(base['color']):
        others = [r for r in runs if not is_accent(r['color'])]
        if others:
            base = copy.deepcopy(others[0])
    # 強調色＝手本で地の色と違う色の文字（紺地の黄色など）。無ければ赤っぽい色・それも無ければ手本の赤
    diff = [r['color'] for r in runs if r['text'].strip() and r['color'] and r['color'] != base['color']]
    accent = diff[0] if diff else next((r['color'] for r in runs if is_accent(r['color'])), '#B4242C')
    para = copy.deepcopy(tx['paras'][0]) if tx['paras'] else {}
    w, h = L['box'][2], L['box'][3]
    size, nh = fit_size(re.sub(r'\\?[【】]', '', s), w, h, base['size'] or 18, para.get('lineSpacing') or 100)
    if nh > h:                                  # 箱を下へ伸ばす（上の位置はそのまま）
        L['h'] *= nh / h
        L['box'][3] = nh
    L['_moji'] = {'size0': base['size'] or 18, 'size': size, 'h0': h, 'h': L['box'][3], 'iro': base.get('color'), 'kyouchou': accent}
    base['size'] = size
    newruns, n = [], 0
    paras = []
    for k, line in enumerate(s.split('\n')):
        rs, ln = runs_from(line + '\n', base, accent)
        for r in rs:
            r['start'] += n
            r['end'] += n
        newruns += rs
        p = copy.deepcopy(para)
        p['start'], p['end'] = n, n + ln
        paras.append(p)
        n += ln
    L['text'] = {'content': ''.join(r['text'] for r in newruns), 'runs': newruns, 'paras': paras, 'lists': False}


HAIKEI = ('背景（全面）', '帯・線')


def aki_haba(pg, L, cat):
    """人物の枠の左右の空き（pt）。同じ高さにある文字・板・絵の手前まで広げてよい。枠を囲む板があればその内側"""
    x, y, w, h = L['box']
    cx = x + w / 2
    lo, hi = 14.0, 706.0
    for o in pg['layers']:
        if o is L or o['kind'] == 'group':
            continue
        ox, oy, ow, oh = o['box']
        if ow * oh <= 4 or (ow >= 700 and oh >= 380):
            continue
        f = o.get('fill') or {}
        if f.get('media') and cat.get(f['media'], '') in HAIKEI:
            continue
        if not ((o.get('text') or {}).get('content', '').strip() or f.get('type') in ('solid', 'blip', 'grad', 'gradient')):
            continue
        if min(y + h, oy + oh) - max(y, oy) < 0.15 * h:
            continue
        if ox <= x + 1 and ox + ow >= x + w - 1:          # 枠を囲む板
            lo, hi = max(lo, ox + 4), min(hi, ox + ow - 4)
        elif ox + ow <= cx:
            lo = max(lo, ox + ow + 6)
        elif ox >= cx:
            hi = min(hi, ox - 6)
    return lo, hi


def icon_slots(layers, cat):
    """差し替える線画アイコンの層（読む順＝上の段から左へ）。同じページで同じ絵をくり返す物（カードの間の矢印・チェック印）と
    横に長い帯（幅200pt以上）は飾りとして手本のまま残す（11/03 p43：矢印3つをアイコンに数えて7個になった）"""
    cnt = {}
    for L in layers:
        m = (L.get('fill') or {}).get('media')
        if m:
            cnt[m] = cnt.get(m, 0) + 1
    ic = [L for L in layers if '線画アイコン' in cat.get((L.get('fill') or {}).get('media') or '', '')
          and 20 < L['box'][3] < 130 and L['box'][1] > 30 and L['box'][2] < 200 and cnt[L['fill']['media']] == 1]
    ic.sort(key=lambda L: (round(L['box'][1] / 40), L['box'][0]))
    return ic


def swap_hito(L, mood, pg=None, cat=None, used=None):
    """人物の絵を差し替える。気持ちの候補の中から、枠の高さのまま横の空きに収まり一番大きく描ける絵を選ぶ
    （11/01 質問2：縦長の枠に横長の絵を選び、横幅1.3倍で縮めて高さが56%になった）。同じ資料で使った絵は後回し"""
    import make
    from PIL import Image
    keys = make.HITO.get(mood)
    if not keys:
        return
    a, b, tx, c, d, ty = L['m']
    sx, sy = math.hypot(a, c), math.hypot(b, d)
    W, H = L['w'] * sx, L['h'] * sy
    cx = tx + W / 2
    if pg is not None:
        lo, hi = aki_haba(pg, L, cat or {})
        maxw = max(W, min(2 * min(cx - lo, hi - cx), H * 2.0))
    else:
        maxw = W * 1.3
    cand = []
    for k in keys:
        # 手本の人物はソコストの色つき版（黒の線・グレーのスーツ・青のネクタイ）。無ければ線だけの版
        f = os.path.join(D, 'assets', 'soco_color', k + '.png')
        if not os.path.exists(f):
            f = os.path.join(D, 'assets', 'soco', k + '.png')
        if not os.path.exists(f):
            continue
        iw, ih = Image.open(f).size
        nw, nh = H * iw / ih, H               # 高さはそのまま、横幅を絵の縦横比に
        if nw > maxw:                         # 横の空きに収まらなければ縮める（下をそろえる・隣にかぶせない）
            nw, nh = maxw, maxw * ih / iw
        cand.append((-(used or {}).get(k, 0), round(nh, 1), -zlib.crc32((L['id'] + k).encode()), k, f, nw, nh))
    if not cand:
        return
    _, _, _, k, f, nw, nh = max(cand)
    if used is not None:
        used[k] = used.get(k, 0) + 1
    L['m'] = [1, 0, cx - nw / 2, 0, 1, ty + H - nh]
    L['w'], L['h'] = nw, nh
    L['box'] = [cx - nw / 2, ty + H - nh, nw, nh]
    L['fill'] = {'type': 'blip', 'alpha': 1.0, 'src': None, 'fillRect': None, 'media': f}
    L['kind'] = 'blip'
    L['_sashikae'] = {'shu': 'hito', 'moto_box': [tx, ty, W, H], 'e': k}


def dark_under(tehon_png, box):
    """手本の画像で、その箱のまわりの暗い画素の割合（0〜1・紺の帯の上なら大きい）"""
    from PIL import Image
    if not tehon_png or not os.path.exists(tehon_png):
        return 0.0
    im = Image.open(tehon_png).convert('L')
    k = im.size[0] / 720.0
    x, y, w, h = [v * k for v in box]
    m = 6 * k
    parts = [(x - m, y - m, x + w + m, y), (x - m, y + h, x + w + m, y + h + m),
             (x - m, y, x, y + h), (x + w, y, x + w + m, y + h)]
    dark = tot = 0
    for p in parts:
        p = tuple(int(max(0, min(v, im.size[i % 2] - 1))) for i, v in enumerate(p))
        if p[2] > p[0] and p[3] > p[1]:
            px = im.crop(p).tobytes()
            dark += sum(1 for v in px if v < 100)
            tot += len(px)
    return dark / tot if tot else 0.0


ICON_IRO = {'kuro': (26, 26, 26), 'shiro': (255, 255, 255), 'aka': (180, 36, 44)}


def ink_bbox(im):
    """絵の線がある所（左, 上, 右, 下）を 0〜1 の割合で。透過があれば不透明の所・無ければ白くない所"""
    im = im.convert('RGBA')
    if im.getextrema()[3][0] < 255:
        m = im.getchannel('A').point(lambda v: 255 if v > 40 else 0)
    else:
        m = im.convert('L').point(lambda v: 255 if v < 200 else 0)
    bb = m.getbbox() or (0, 0) + im.size
    return bb[0] / im.size[0], bb[1] / im.size[1], bb[2] / im.size[0], bb[3] / im.size[1]


def moto_iro(path):
    """手本のアイコンの色の系統（kuro／shiro／aka）。読めなければ None"""
    from PIL import Image
    try:
        im = Image.open(path).convert('RGBA').resize((64, 64))
    except Exception:
        return None
    px = [p for p in im.getdata() if p[3] > 128]
    if not px:
        return None
    r = sum(p[0] for p in px) / len(px)
    g = sum(p[1] for p in px) / len(px)
    b = sum(p[2] for p in px) / len(px)
    if r > 200 and g > 200 and b > 200:
        return 'shiro'
    if r - b > 60 and r - g > 60:
        return 'aka'
    return 'kuro'


def swap_icon(L, name, iro='kuro', moto=None):
    """線画アイコンを差し替える。手本の絵の【線がある所】（moto＝手本の画像ファイル）に収める
    （11/01 仕事1：枠いっぱいに置き、手本の絵の上の余白に乗っていた文字と重なった）"""
    from PIL import Image
    f = os.path.join(D, 'assets', 'icon', name + '.png')
    if not os.path.exists(f):
        print('アイコンが無い', name, file=sys.stderr)
        return
    out = os.path.join(D, 'assets', 'icon_navy')
    os.makedirs(out, exist_ok=True)
    g = os.path.join(out, name + ('' if iro == 'kuro' else '_' + iro) + '_k.png')
    if not os.path.exists(g):
        im = Image.open(f).convert('RGBA')
        a = im.getchannel('A') if im.getextrema()[3][0] < 255 else im.convert('L')
        if im.getextrema()[3][0] == 255:        # 透過の無い白黒（P）なら暗い所を線とみなす
            a = a.point(lambda v: 255 - v)
        c = Image.new('RGBA', im.size, ICON_IRO[iro] + (255,))
        c.putalpha(a)
        c = c.crop(c.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox() or (0, 0) + c.size)  # 線の所だけに切る
        c.save(g)
    a_, b_, tx, c_, d_, ty = L['m']
    W, H = L['w'] * math.hypot(a_, c_), L['h'] * math.hypot(b_, d_)
    x0, y0, x1, y1 = 0, 0, 1, 1
    if moto and os.path.exists(moto):
        try:
            x0, y0, x1, y1 = ink_bbox(Image.open(moto))
        except Exception:
            pass
    bx, by, bw, bh = tx + W * x0, ty + H * y0, W * (x1 - x0), H * (y1 - y0)
    iw, ih = Image.open(g).size
    k = min(bw / iw, bh / ih)
    nw, nh = iw * k, ih * k
    L['m'] = [1, 0, bx + (bw - nw) / 2, 0, 1, by + (bh - nh) / 2]
    L['w'], L['h'] = nw, nh
    L['box'] = [bx + (bw - nw) / 2, by + (bh - nh) / 2, nw, nh]
    L['fill'] = {'type': 'blip', 'alpha': 1.0, 'src': None, 'fillRect': None, 'media': g}
    L['kind'] = 'blip'
    L['_sashikae'] = {'shu': 'icon', 'moto_box': [tx, ty, W, H], 'e': name, 'iro': iro}


def main():
    w, spec_f, out = sys.argv[1:4]
    cat = json.load(open(os.path.join(w, 'sozai', 'bunrui.json')))
    types = {t['name']: t for t in json.load(open(os.path.join(w, 'kata-types.json')))}
    os.makedirs(os.path.join(out, 'sou'), exist_ok=True)
    made = []
    used = {}
    for i, sp in enumerate(json.load(open(spec_f))):
        base = sp.get('base') or types[sp['kata']]['pages'][0]
        pg = json.load(open(os.path.join(w, 'sou', f'p{base:03d}.json')))
        pg = copy.deepcopy(pg)
        slots = order(pg['layers'])
        moji = sp.get('moji', [])
        drop = set()
        moto_box = {L['id']: list(L['box']) for L in slots}
        for k, L in enumerate(slots):
            if k < len(moji):
                fill_text(L, moji[k])
            else:
                drop.add(L['id'])
        mejirushi = set()
        # 手本の1語だけに敷いた目印（マーカーの小さな板）は、文を入れ替えると位置がずれるので外す
        # （11/03 試し6枚目：「自分」の下のベージュの板が「4つの仕事」の後ろに残った）
        for L in slots:
            if L['id'] in drop:
                continue
            bx, by, bw, bh = moto_box[L['id']]
            for O in pg['layers']:
                if O['kind'] not in ('vec', 'shape') or (O.get('text') or {}).get('content', '').strip():
                    continue
                ox, oy, ow, oh = O['box']
                if (ox >= bx - 4 and ox + ow <= bx + bw + 4 and ow < 0.35 * bw and oh <= bh * 1.5
                        and min(by + bh, oy + oh) - max(by, oy) >= 0.7 * oh):
                    mejirushi.add(O['id'])
        pg['layers'] = [L for L in pg['layers'] if L['id'] not in mejirushi]
        for L in pg['layers']:
            if L['id'] in drop:
                L.pop('text', None)
                if L['kind'] == 'text':
                    L['kind'] = 'shape'
        if sp.get('hito'):
            # 差し替えるのはスーツの1人の人物の絵だけ（キャラクター・ロボット・何人か・物は手本の絵のまま・assets/hito_sashikae.json）
            ok = set(json.load(open(os.path.join(D, 'assets', 'hito_sashikae.json')))['ok'])
            for L in pg['layers']:
                m = (L.get('fill') or {}).get('media')
                if m in ok and L['box'][3] > 60:
                    swap_hito(L, sp['hito'], pg, cat, used)
        if sp.get('icon'):
            ic = icon_slots(pg['layers'], cat)
            tp = os.path.join(w, 'tehon-img', f'p{base:03d}.png')
            for L, name in zip(ic, sp['icon']):
                moto = os.path.join(w, 'pptx', 'x', 'ppt', 'media', L['fill']['media'])
                iro = moto_iro(moto)                  # 手本のアイコンと同じ色の系統（11/01 STOP の赤→黒い時計になった）
                if not iro:
                    r = dark_under(tp, L['box'])      # 読めなければ前の決め方：暗い所が6割超→白／2〜6割→赤／それ以下→黒
                    iro = 'shiro' if r > 0.6 else 'aka' if r > 0.2 else 'kuro'
                swap_icon(L, name, iro, moto)
        n = 9001 + i
        pg['page'] = n
        pg['moto'] = base
        json.dump(pg, open(os.path.join(out, 'sou', f'p{n}.json'), 'w'), ensure_ascii=False)
        made.append(n)
    print(' '.join(map(str, made)))


if __name__ == '__main__':
    main()
