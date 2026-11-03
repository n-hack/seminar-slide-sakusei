#!/usr/bin/env python3
"""kekka.json（全周の数字）から、ページごとの最新の差と合否の表を出す（kekka.md に貼る用）。

使い方  python3 kekka_hyou.py <作業フォルダ> [周の名前 ...（新しい順に優先。省略時は kekka.json の後ろほど新しい）]
合格の線  違う所（ratio）3% 以下 かつ ssim 0.985 以上（800×450 に縮めて比べた値）
"""
import json, os, sys

RATIO_MAX, SSIM_MIN = 3.0, 0.985


def main():
    w = sys.argv[1]
    k = json.load(open(os.path.join(w, 'kekka.json')))
    order = sys.argv[2:] or list(k)[::-1]
    kata = json.load(open(os.path.join(w, 'kata-index.json')))['page2kata']
    best = {}
    for name in order:
        for p, v in k.get(name, {}).items():
            best.setdefault(int(p), (name, v))
    ok = 0
    print('| ページ | 型 | 周 | mad | 違う所% | ssim | 合否 |')
    print('|---|---|---|---|---|---|---|')
    for p in sorted(best):
        name, v = best[p]
        good = v['ratio'] <= RATIO_MAX and v['ssim'] >= SSIM_MIN
        ok += good
        print(f"| {p} | {kata.get(str(p), '-')} | {name} | {v['mad']} | {v['ratio']} | {v['ssim']} | {'合格' if good else '不合格'} |")
    rs = [v['ratio'] for _, v in best.values()]
    print(f'\n作り直した {len(best)} 枚・合格 {ok} 枚・違う所の平均 {sum(rs) / len(rs):.2f}%・最大 {max(rs)}%')


if __name__ == '__main__':
    main()
