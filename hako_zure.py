#!/usr/bin/env python3
"""文字の箱ごとに、手本と作り直しの画像がいちばん合うずらし量（1600px の画素）を測る。

使い方  python3 hako_zure.py <作業フォルダ> <周:ページ,ページ…> [<周:…> …]
  例    python3 hako_zure.py . shuu3:825,327 shuu1_kisoku:3,43
出す物  1行1箱：ページ 箱 縦位置 行間% 大きさ 揃え 箱の幅 段落数 元の違い% 最良dx 最良dy
        最後に (揃え, 行間) ごとの dx の数え
dx が正 ＝ 作り直しを右へずらすと手本に合う（＝作り直しが左にずれている）
"""
import json, os, sys, collections
import numpy as np
from PIL import Image

K = 1600 / 720


def boxes(w, rnd, p):
    a = np.asarray(Image.open(os.path.join(w, 'tehon-img', f'p{p:03d}.png')).convert('L')).astype(int)
    b = np.asarray(Image.open(os.path.join(w, rnd, 'img', f'p{p:03d}.png')).convert('L')).astype(int)
    pg = json.load(open(os.path.join(w, 'sou', f'p{p:03d}.json')))
    for L in pg['layers']:
        t = L.get('text')
        if not t or not t['content'].strip():
            continue
        x, y, bw, bh = L['box']
        x0, y0 = max(int(x * K) - 4, 4), max(int(y * K) - 4, 4)
        x1, y1 = min(int((x + bw) * K) + 4, 1596), min(int((y + bh) * K) + 4, 896)
        if x1 - x0 < 20 or y1 - y0 < 10:
            continue
        A = a[y0:y1, x0:x1]
        base = (np.abs(A - b[y0:y1, x0:x1]) > 32).mean()
        if base < 0.005:
            continue
        best = None
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                B = b[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
                if B.shape != A.shape:
                    continue
                v = (np.abs(A - B) > 32).mean()
                if best is None or v < best[0]:
                    best = (v, dx, dy)
        ls = round(max([q.get('lineSpacing') or 100 for q in t['paras']] or [100]))
        al = (t['paras'][0].get('align') if t['paras'] else None) or 'START'
        sz = max([r['size'] or 0 for r in t['runs'] if r['text'].strip()] or [0])
        yield (p, L['id'], L.get('contentAlignment') or 'TOP', ls, round(sz, 1), al, round(bw, 1),
               len(t['paras']), round(base * 100, 1), round(best[0] * 100, 1), best[1], best[2])


def main():
    w = sys.argv[1]
    rows = []
    for arg in sys.argv[2:]:
        rnd, ps = arg.split(':')
        for p in ps.split(','):
            rows += list(boxes(w, rnd, int(p)))
    for r in rows:
        print(*r)
    c = collections.defaultdict(collections.Counter)
    for r in rows:
        c[r[5]][(r[10], r[11])] += 1
    print('--- 揃えごとの (dx,dy) の数')
    for k, v in sorted(c.items()):
        print(k, dict(v.most_common()))


if __name__ == '__main__':
    main()
