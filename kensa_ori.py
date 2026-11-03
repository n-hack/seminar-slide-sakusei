#!/usr/bin/env python3
"""オリジナル作成（orijinaru.py → fukusei.py build）で作ったページを、画像で数えて合否を出す門。不合格なら URL を出さない。

使い方  python3 kensa_ori.py <作業フォルダ W> <出す先 OUT>
  OUT/daihon-kata.json（tsukuru.py が書く・各ページの base）・OUT/sou/p9001.json…（orijinaru.py が書く）
  OUT/img/p001.png…（sa.py thumbs で取った作ったページの画像・幅1600）・W/tehon-img/pNNN.png（手本の画像）
  → OUT/kensa.json と画面に1ページ1行。終わりのコードは 不合格0枚で 0、あれば 1

数えること（1pt＝1600/720 画素）
  hamidashi … 文字・差し替えた絵の「置いてよい所」の外で、手本と色が違う画素（差48超・3×3で孤立点を除く）の数。
               置いてよい所＝文字の箱（新しい箱と手本の箱）＋差し替えた絵（新旧の枠）＋消した文字の箱。字が箱からはみ出すとここに出る
  kasanari  … 文字の行が実際に乗る所（行数×行の高さ・箱の揃えで上下を決める）と、絵（差し替えた絵・手本の人物とアイコン）や
               ほかの文字との重なり。手本の同じ組より増えた分だけ数える（手本の重なりは手本の作り）
  moji      … 文字の大きさ。画像で字の高さ（行ごとの字の画素の高さの中央値）を測り、字の大きさに直す（漢字の高さ≒0.88字）。
               10pt 未満か、手本の同じ箱の 7割未満なら不合格。台本の上でも 0.75 倍未満に縮めていたら不合格
  amari     … 箱の余り。字の画素の数を手本の同じ箱と比べ、手本の 35% 未満なら不合格（手本の字の画素が 400 以上の箱だけ）
  kieta     … 文字を入れた箱に字の画素が無い（60 未満）
  hito      … 差し替えた人物の高さが手本の枠の 75% 未満
"""
import json, os, sys, math, re, glob

import numpy as np
from PIL import Image

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from orijinaru import order, haba

K = 1600 / 720.0
SEN = {'hamidashi_px': 900, 'kasanari_pt2': 60.0, 'moji_pt': 10.0, 'moji_hi': 0.70, 'size_hi': 0.75,
       'amari_hi': 0.35, 'amari_min_px': 400, 'kieta_px': 60, 'hito_hi': 0.75}


def rgb(hx):
    hx = (hx or '#000000').lstrip('#')
    return np.array([int(hx[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)


def px_rect(b, pad=0.0, H=900, W=1600):
    x, y, w, h = b
    x0, y0 = int(max(0, (x - pad) * K)), int(max(0, (y - pad) * K))
    x1, y1 = int(min(W, (x + w + pad) * K)), int(min(H, (y + h + pad) * K))
    return x0, y0, max(x0, x1), max(y0, y1)


def gyou_rect(L):
    """文字の行が実際に乗る所（pt）。行の数は orijinaru と同じ物差し（1字＝大きさの正方形）で数える"""
    tx = L['text']
    runs = [r for r in tx['runs'] if r['text'].strip()] or tx['runs']
    s = max(runs, key=lambda r: len(r['text']))['size'] or 18
    ls = (tx['paras'][0].get('lineSpacing') if tx['paras'] else None) or 100
    x, y, w, h = L['box']
    per = max(1, int(w / s))
    lines = [l for l in tx['content'].rstrip('\n').split('\n')]
    n = sum(max(1, math.ceil(haba(l) / per)) for l in lines) if lines else 1
    th = n * s * 1.45 * ls / 100.0
    al = L.get('contentAlignment') or 'TOP'
    ins = L.get('inset') or {}
    top = y + (ins.get('t') or 0)
    if al == 'MIDDLE':
        top = y + (h - th) / 2
    elif al == 'BOTTOM':
        top = y + h - th - (ins.get('b') or 0)
    return [x, top, w, th], s


def iro_list(L):
    tx = L.get('text') or {}
    cs = {r.get('color') for r in tx.get('runs', []) if r.get('text', '').strip() and r.get('color')}
    return [rgb(c) for c in cs] or [rgb('#1A1A1A')]


def ink(img, rect, iros, tol=70):
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0:
        return np.zeros((0, 0), bool)
    a = img[y0:y1, x0:x1].astype(np.int16)
    m = np.zeros(a.shape[:2], bool)
    # 地の色に近い字の色は数えない（11/03 p393：黒の run が紺の帯と同じに数えられ、手本の字の画素が130,000と出た）
    # 箱の4割超を占める色は字ではなく地として外す
    for c in iros:
        mc = np.abs(a - c).max(axis=2) < tol
        if mc.mean() <= 0.4:
            m |= mc
    return m


def ji_takasa(m):
    """字の行ごとの高さ（画素）の中央値。字の無い行で区切る"""
    if m.size == 0:
        return 0.0
    rows = m.sum(axis=1) >= 2
    runs, n = [], 0
    for v in list(rows) + [False]:
        if v:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    runs = [r for r in runs if r >= 4]
    return float(np.median(runs)) if runs else 0.0


def jitsu_rect(img, T):
    """文字の行が実際に乗っている所（pt）。箱の中で字の色の画素がある範囲（無ければ物差しの見積もり）。
    11/03 質問2：見積もりは1行を2行と数え、絵と重なっていないのに重なりと出た"""
    m = ink(img, px_rect(T['box']), iro_list(T))
    if m.size and m.sum() >= 60:
        ys, xs = np.nonzero(m)
        x0, y0, _, _ = px_rect(T['box'])
        return [(x0 + xs.min()) / K, (y0 + ys.min()) / K, (xs.max() - xs.min() + 1) / K, (ys.max() - ys.min() + 1) / K]
    return gyou_rect(T)[0]


def kasanari(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def e_box(L, cat):
    """絵の線のある所（pt）。差し替えた絵は線の所に切ってあるので枠のまま・手本の絵は素材の線の所で縮める"""
    return L['box']


def ichi(w, out, n, base, pg):
    tp = json.load(open(os.path.join(w, 'sou', f'p{base:03d}.json')))
    t_by = {L['id']: L for L in tp['layers']}
    gen = np.asarray(Image.open(os.path.join(out, 'img', f'p{n:03d}.png')).convert('RGB').resize((1600, 900)))
    teh = np.asarray(Image.open(os.path.join(w, 'tehon-img', f'p{base:03d}.png')).convert('RGB').resize((1600, 900)))
    cat = json.load(open(os.path.join(w, 'sozai', 'bunrui.json')))
    # 前の版（11/01・印なし）で作ったページも数えられるように、印が無ければ手本と比べて付ける
    t_slot_ids = {L['id'] for L in order(tp['layers'])}
    for L in pg['layers']:
        tl = t_by.get(L['id'])
        if tl is None:
            continue
        if not L.get('_moji') and L['id'] in t_slot_ids and (L.get('text') or {}).get('content', '').strip():
            sz = lambda X: max(([r for r in X['text']['runs'] if r['text'].strip()] or X['text']['runs']), key=lambda r: len(r['text']))['size'] or 18
            L['_moji'] = {'size': sz(L), 'size0': sz(tl)}
        m = str((L.get('fill') or {}).get('media') or '')
        if not L.get('_sashikae') and ('/soco' in m or '/icon_navy/' in m):
            L['_sashikae'] = {'shu': 'hito' if '/soco' in m else 'icon', 'moto_box': tl['box'], 'e': os.path.basename(m)}
    fu = []
    kazu = {}
    # ---- はみ出し
    yoi = np.zeros((900, 1600), bool)
    t_slots = {L['id'] for L in order(tp['layers'])}
    for L in pg['layers']:
        if L['id'] in t_slots or L.get('_moji') or L.get('_sashikae'):
            for b, pad in ((L['box'], 6), (t_by.get(L['id'], L)['box'], 6)):
                x0, y0, x1, y1 = px_rect(b, pad)
                yoi[y0:y1, x0:x1] = True
            if L.get('_sashikae'):
                x0, y0, x1, y1 = px_rect(L['_sashikae']['moto_box'], 4)
                yoi[y0:y1, x0:x1] = True
    sa = np.abs(gen.astype(np.int16) - teh.astype(np.int16)).max(axis=2) > 48
    # 手本を作り直したときにも出る差（枠の細い線・帯の端の描き方）は、はみ出しに数えない
    # （11/03 p48：カードの縁と下の帯の1画素の線が987画素に積もって不合格になった）
    moto = sorted(glob.glob(os.path.join(w, 'z*', 'img', f'p{base:03d}.png')))
    if moto:
        reb = np.asarray(Image.open(moto[-1]).convert('RGB').resize((1600, 900)))
        r0 = np.abs(reb.astype(np.int16) - teh.astype(np.int16)).max(axis=2) > 48
        r1 = r0.copy()
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                r1 |= np.roll(np.roll(r0, dy, 0), dx, 1)
        sa &= ~r1
    soto = sa & ~yoi
    e = soto.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            e &= np.roll(np.roll(soto, dy, 0), dx, 1)
    kazu['hamidashi_px'] = int(e.sum())
    if e.sum() > SEN['hamidashi_px']:
        ys, xs = np.nonzero(e)
        fu.append(f"はみ出し {int(e.sum())}画素（{int(xs.min() / K)},{int(ys.min() / K)}〜{int(xs.max() / K)},{int(ys.max() / K)}pt）")
    # ---- 重なり（手本より増えた分）
    moji = [L for L in pg['layers'] if L.get('_moji') and (L.get('text') or {}).get('content', '').strip()]
    e_layers = [L for L in pg['layers'] if L['kind'] == 'blip' and (L.get('_sashikae') or
                ('イラスト' in cat.get((L.get('fill') or {}).get('media') or '', '') or
                 '線画アイコン' in cat.get((L.get('fill') or {}).get('media') or '', '')))
                and L['box'][2] < 700]
    kmax = 0.0
    for i, T in enumerate(moji):
        r = jitsu_rect(gen, T)
        tr = jitsu_rect(teh, t_by[T['id']]) if T['id'] in t_by and (t_by[T['id']].get('text') or {}).get('content', '').strip() else None
        aite = [(E, E['box'], t_by.get(E['id'], E)['box'] if not E.get('_sashikae') else E['_sashikae']['moto_box']) for E in e_layers]
        aite += [(U, jitsu_rect(gen, U), jitsu_rect(teh, t_by[U['id']]) if U['id'] in t_by and (t_by[U['id']].get('text') or {}).get('content', '').strip() else None)
                 for U in moji[i + 1:]]
        for E, eb, teb in aite:
            a = kasanari(r, eb)
            a0 = kasanari(tr, teb) if (tr and teb) else 0.0
            if a - a0 * 1.5 > SEN['kasanari_pt2']:
                kmax = max(kmax, a - a0)
                nm = (E.get('_sashikae') or {}).get('e') or ((E.get('text') or {}).get('content', '')[:8] if E.get('text') else (E.get('fill') or {}).get('media', ''))
                fu.append(f"重なり「{T['text']['content'][:10].strip()}」と「{os.path.basename(str(nm))[:14]}」{a:.0f}pt²（手本 {a0:.0f}）")
    kazu['kasanari_pt2'] = round(kmax, 1)
    # ---- 文字の大きさ・箱の余り・消えた字
    for T in moji:
        tl = t_by.get(T['id'])
        r, s = gyou_rect(T)
        m = ink(gen, px_rect(T["box"], 2), iro_list(T))
        n_px = int(m.sum())
        h = ji_takasa(m) / K / 0.88
        mm = T['_moji']
        rec = {'moji': T['text']['content'][:16].replace('\n', '/'), 'size': round(mm['size'], 1), 'size0': mm['size0'], 'px': n_px, 'mitate_pt': round(h, 1)}
        if tl is not None and (tl.get('text') or {}).get('content', '').strip():
            tr, ts = gyou_rect(tl)
            tm = ink(teh, px_rect(tl["box"], 2), iro_list(tl))
            rec['tehon_px'] = int(tm.sum())
            rec['tehon_mitate_pt'] = round(ji_takasa(tm) / K / 0.88, 1)
        kazu.setdefault('hako', []).append(rec)
        if n_px < SEN['kieta_px']:
            fu.append(f"字が出ていない「{rec['moji']}」（{n_px}画素）")
            continue
        if mm['size'] < mm['size0'] * SEN['size_hi']:
            fu.append(f"字を縮めすぎ「{rec['moji']}」{mm['size0']}→{mm['size']:.1f}pt（文字数を減らす）")
        if h and (h < SEN['moji_pt'] or (rec.get('tehon_mitate_pt') and h < rec['tehon_mitate_pt'] * SEN['moji_hi'])):
            fu.append(f"字が小さい「{rec['moji']}」画像で{h:.1f}pt（手本 {rec.get('tehon_mitate_pt')}）")
        if rec.get('tehon_px', 0) >= SEN['amari_min_px'] and n_px < rec['tehon_px'] * SEN['amari_hi']:
            fu.append(f"箱の余り「{rec['moji']}」字の画素 {n_px}（手本 {rec['tehon_px']}・{n_px / rec['tehon_px']:.0%}）")
    # ---- 人物の大きさ
    for L in pg['layers']:
        sk = L.get('_sashikae')
        if sk and sk['shu'] == 'hito':
            # 置いた絵の高さは h×縦の倍率（11/01 の版は box を直していないので box では測れない）
            hi = L['h'] * math.hypot(L['m'][1], L['m'][4]) / sk['moto_box'][3]
            kazu.setdefault('hito_hi', []).append(round(hi, 2))
            if hi < SEN['hito_hi']:
                fu.append(f"人物が小さい（手本の枠の高さの {hi:.0%}）")
    return fu, kazu


def main():
    w, out = sys.argv[1:3]
    dk = json.load(open(os.path.join(out, 'daihon-kata.json')))
    res, ng = [], 0
    for i, sp in enumerate(dk):
        n = 9001 + i
        pg = json.load(open(os.path.join(out, 'sou', f'p{n}.json')))
        fu, kazu = ichi(w, out, i + 1, pg['moto'], pg)
        ng += bool(fu)
        res.append({'mai': i + 1, 'base': pg['moto'], 'goukaku': not fu, 'fugoukaku': fu, 'kazu': kazu})
        print(f"{i + 1:2d}枚目 手本p{pg['moto']:<4d} {'合格' if not fu else '不合格'}  はみ出し{kazu['hamidashi_px']}画素 重なり{kazu['kasanari_pt2']}pt²"
              + ('  ' + ' ／ '.join(fu) if fu else ''))
    json.dump({'sen': SEN, 'pages': res, 'fugoukaku': ng}, open(os.path.join(out, 'kensa.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'不合格 {ng} / {len(res)} 枚')
    sys.exit(1 if ng else 0)


if __name__ == '__main__':
    main()
