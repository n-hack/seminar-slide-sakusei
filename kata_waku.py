#!/usr/bin/env python3
"""867型ごとに「文字の箱の数・箱ごとの文字数の上限・人物とアイコンの数・作り直しの合否」を表にする（オリジナル作成の型選び用）。

使い方  python3 kata_waku.py <作業フォルダ>      → <作業フォルダ>/kata-waku.json と kata-waku.md
表の中身（1型＝1行）
  hako   … 文字の箱（orijinaru.py が moji を入れる順＝上から・同じ高さなら左から）
           w・h（pt）・size（手本の字の大きさ）・moto（手本の文）・jisuu（手本の字数）
           jougen … 手本の大きさのまま箱に入る字数（1字＝字の大きさの正方形・行の高さ＝大きさ×1.45×行間・orijinaru.fit_size と同じ物差し）
           gyou   … 入る行の数
  hito   … 差し替えられる人物の絵の数（イラストで高さ60pt超）／icon … 差し替えられる線画アイコンの数
  goukaku… 手本の作り直しが合格の線（違う所3%以下・ssim0.985以上）を通ったか（kekka*.json の一番良い周）
  dame   … 型選びに使わない理由（写真・画面の切り抜き／動画／文字の箱が0）
"""
import json, os, sys, math, glob

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from orijinaru import order, icon_slots, haba

RATIO_MAX, SSIM_MIN = 3.0, 0.985


def gyou_jougen(w, h, s, ls):
    """手本の大きさ s のまま入る（1行の字数, 行数）。orijinaru.fit_size の「入る」の線（h×1.35＋s）に合わせる"""
    per = max(1, int(w / s))
    lh = s * 1.45 * (ls / 100.0)
    return per, max(1, int((h * 1.35 + s) / lh))


def tsukaeru_haba(L, layers, cat):
    """文字が実際に置ける幅（pt）。箱を囲む枠の内側に切り、同じ高さに重なる絵（人物・アイコン）の手前で止める。
    中央揃えは中心から近い方の端までの2倍（11/03 試し：枠より広い箱で文が枠の外へ／人物が乗る箱で文が人物の下へ）"""
    x, y, w, h = L['box']
    lo, hi = max(x, 8.0), min(x + w, 712.0)
    cy = y + h / 2
    for O in layers:
        if O is L or O['kind'] == 'group':
            continue
        ox, oy, ow, oh = O['box']
        if ow >= 700 or ow * oh <= 4:
            continue
        m = (O.get('fill') or {}).get('media')
        sozai = cat.get(m, '') if m else ''
        if sozai.startswith('背景') or sozai.startswith('帯'):
            continue
        if O['kind'] in ('vec', 'shape') and not (O.get('text') or {}).get('content', '').strip():
            # 枠：箱の左端の少し内側と縦の真ん中を含む、箱より狭い形
            if ox <= x + 10 <= ox + ow and oy <= cy <= oy + oh and ow < w:
                hi = min(hi, ox + ow - 6)
            continue
        if ('イラスト' in sozai or '線画アイコン' in sozai) and min(y + h, oy + oh) - max(y, oy) >= 0.3 * h:
            if ox + ow <= lo or ox >= hi or ox <= x + w / 2 <= ox + ow:
                continue                                  # 横に無い絵・文字の後ろに敷いた絵（枠の画像）は数えない
            if ox + ow / 2 >= (lo + hi) / 2:
                hi = min(hi, ox - 4)
            else:
                lo = max(lo, ox + ow + 4)
    al = (L['text']['paras'][0].get('align') if L['text']['paras'] else None) or 'START'
    if al == 'CENTER':
        cx = x + w / 2
        return max(0.0, 2 * min(cx - lo, hi - cx))
    return max(0.0, hi - lo)


def goukaku_hyou(w):
    best = {}
    for f in sorted(glob.glob(os.path.join(w, 'kekka*.json'))):
        for _, d in json.load(open(f)).items():
            for p, v in d.items():
                ok = v['ratio'] <= RATIO_MAX and v['ssim'] >= SSIM_MIN
                p = int(p)
                if p not in best or (ok and not best[p][0]) or (ok == best[p][0] and v['ratio'] < best[p][1]):
                    best[p] = (ok, v['ratio'])
    return best


def main():
    w = sys.argv[1]
    cat = json.load(open(os.path.join(w, 'sozai', 'bunrui.json')))
    K = json.load(open(os.path.join(w, 'kata-zenbu.json')))['kata']
    gk = goukaku_hyou(w)
    out = []
    for k in K:
        p = k['page']
        pg = json.load(open(os.path.join(w, 'sou', f'p{p:03d}.json')))
        hako = []
        for L in order(pg['layers']):
            tx = L['text']
            runs = [r for r in tx['runs'] if r['text'].strip()] or tx['runs']
            s = max(runs, key=lambda r: len(r['text']))['size'] or 18
            ls = (tx['paras'][0].get('lineSpacing') if tx['paras'] else None) or 100
            bw, bh = tsukaeru_haba(L, pg['layers'], cat), L['box'][3]
            per, n = gyou_jougen(bw, bh, s, ls)
            moto = tx['content'].strip()
            # 手本が実際に置いている1行の長さより厳しくはしない（手本が絵に重ねて置いている箱がある・p16 割れたハート）
            per = max(per, math.ceil(max((haba(l) for l in moto.split('\n')), default=0)))
            per = min(per, int(L['box'][2] / s) or 1)
            hako.append({'w': round(bw, 1), 'h': round(bh, 1), 'size': s, 'moto': moto,
                         'jisuu': len(moto.replace('\n', '').replace(' ', '')),
                         'jougen': per * n, 'gyou': n, 'per': per})
        media = [(L.get('fill') or {}).get('media') for L in pg['layers']]
        hito = sum(1 for L, m in zip(pg['layers'], media) if m and 'イラスト' in cat.get(m, '') and L['box'][3] > 60)
        icon = len(icon_slots(pg['layers'], cat))
        dame = []
        if any(m and '写真' in cat.get(m, '') for m in media):
            dame.append('写真・画面の切り抜き')
        if any(L['kind'] == 'video' for L in pg['layers']):
            dame.append('動画')
        if not hako:
            dame.append('文字の箱が0')
        out.append({'id': k['id'], 'page': p, 'ookii': k['ookii'], 'tsutae': k['tsutae'],
                    'hako': hako, 'hito': hito, 'icon': icon,
                    'goukaku': bool(gk.get(p, (False,))[0]), 'dame': dame})
    json.dump({'kata': out}, open(os.path.join(w, 'kata-waku.json'), 'w'), ensure_ascii=False, indent=0)
    tsukaeru = [o for o in out if o['goukaku'] and not o['dame']]
    with open(os.path.join(w, 'kata-waku.md'), 'w') as f:
        f.write('# 型の箱の表（kata_waku.py が作る・手で直さない）\n\n')
        f.write(f'- 型 {len(out)}・オリジナルに使える型 {len(tsukaeru)}（作り直し合格かつ写真・動画なし）\n')
        f.write(f'- 使えない理由：作り直し不合格 {sum(1 for o in out if not o["goukaku"])}・'
                f'写真/画面 {sum(1 for o in out if "写真・画面の切り抜き" in o["dame"])}・'
                f'動画 {sum(1 for o in out if "動画" in o["dame"])}・文字の箱0 {sum(1 for o in out if "文字の箱が0" in o["dame"])}（重なりあり）\n\n')
        f.write('| 型 | 大きな型 | 伝えたいこと | 箱の数 | 箱ごとの上限（手本の字数） | 人物 | アイコン | 使える |\n|---|---|---|---|---|---|---|---|\n')
        for o in out:
            hk = ' / '.join(f"{h['jougen']}({h['jisuu']})" for h in o['hako'])
            f.write(f"| {o['id']} | {o['ookii']} | {'・'.join(o['tsutae'])} | {len(o['hako'])} | {hk} | {o['hito']} | {o['icon']} | "
                    f"{'○' if o in tsukaeru else '×'} |\n")
    print(f'型 {len(out)}・使える {len(tsukaeru)}')


if __name__ == '__main__':
    main()
