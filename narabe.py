#!/usr/bin/env python3
"""伝えたいことの並び（台本）から、型（kata-zenbu.json）を1ページずつ選んで並べる。同じ型が近くに続かないようにする。

使い方  python3 narabe.py <作業フォルダ> <台本.json> [間を空ける枚数=3]
          台本.json … [{"tsutae": "数字で驚かせる"}, {"tsutae": "手順を見せる", "renban": 4}, {"tsutae": "...", "nitsuzuke": true}, ...]
          renban: N  … その1枚を手本の連番の組（N枚以上）に置き換えて、1つずつ足す演出にする
          nitsuzuke  … 前のページと同じ大きな型をわざと続ける
        python3 narabe.py <作業フォルダ> --tameshi [枚数=800] [間を空ける枚数=3]
          手本の伝えたいことの並びを使って枚数ぶん並べ、続き方を数える（並べ方の試し）
選び方
  1. その伝えたいことが付いた型の中から
  2. 前の「間を空ける枚数」ページに同じ大きな型が無いもの（nitsuzuke の時は逆に同じもの）
  3. その中で一番使った回数が少ない型（同じ型を使い回さない）・同じなら主の伝えたいことが合うもの
"""
import json, os, sys, random, collections


def load(w):
    K = json.load(open(os.path.join(w, 'kata-zenbu.json')))['kata']
    by = collections.defaultdict(list)
    for k in K:
        for t in k['tsutae']:
            by[t].append(k)
    groups = collections.defaultdict(list)
    for k in K:
        if k['renban']:
            groups[k['renban']].append(k)
    return K, by, groups


def narabe(w, daihon, aida=3, seed=0):
    K, by, groups = load(w)
    used = collections.Counter()
    out = []
    rnd = random.Random(seed)
    for d in daihon:
        t = d['tsutae']
        if d.get('renban'):
            gs = [g for g in groups.values() if len(g) >= d['renban']]
            if gs:
                g = min(gs, key=lambda g: (used[g[0]['id']], rnd.random()))
                for k in g[:d['renban']]:
                    used[k['id']] += 1
                    out.append({'tsutae': t, 'kata': k['id'], 'ookii': k['ookii'], 'renban': g[0]['renban']})
                continue
        cand = by.get(t) or K
        mae = [o['ookii'] for o in out[-aida:]]
        if d.get('nitsuzuke') and out:
            c2 = [k for k in cand if k['ookii'] == out[-1]['ookii']]
        else:
            c2 = [k for k in cand if k['ookii'] not in mae or k['ookii'] == 'その他' and 'その他' not in mae[-1:]]
        c2 = c2 or cand
        k = min(c2, key=lambda k: (used[k['id']], k['tsutae'][0] != t, rnd.random()))
        used[k['id']] += 1
        out.append({'tsutae': t, 'kata': k['id'], 'ookii': k['ookii']})
    return out


def kazoe(out, aida):
    seq = [o['ookii'] for o in out]
    run, mx, runs = 1, 1, 0
    for a, b in zip(seq, seq[1:]):
        if a == b:
            run += 1
            mx = max(mx, run)
            if run == 2:
                runs += 1
        else:
            run = 1
    near = sum(1 for i in range(len(seq)) if seq[i] in seq[max(0, i - aida):i])
    ids = collections.Counter(o['kata'] for o in out)
    return {'枚数': len(out), '使った型の数': len(ids), '同じ型を2回以上使った数': sum(1 for v in ids.values() if v > 1),
            '同じ大きな型が続いた所': runs, '最長の続き': mx, f'前{aida}枚に同じ大きな型がある枚数': near}


def main():
    w = sys.argv[1]
    if sys.argv[2] == '--tameshi':
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 800
        aida = int(sys.argv[4]) if len(sys.argv) > 4 else 3
        K = json.load(open(os.path.join(w, 'kata-zenbu.json')))['kata']
        daihon = [{'tsutae': K[i % len(K)]['tsutae'][0]} for i in range(n)]
        tehon = [{'kata': k['id'], 'ookii': k['ookii']} for k in K]
        print('手本の並び', kazoe(tehon[:n], aida))
        out = narabe(w, daihon, aida)
        print('並べた結果（手本と同じ伝えたいことの順）', kazoe(out, aida))
        # 伝えたいことの順を混ぜた台本（同じ伝えたいことが何枚も続かない新しい台本の見立て）
        mz = daihon[:]
        random.Random(1).shuffle(mz)
        print('並べた結果（伝えたいことの順を混ぜた台本）', kazoe(narabe(w, mz, aida), aida))
        # 伝えたいことごとに型の数（足りないと同じ型を使い回す）
        by = collections.Counter(t for k in K for t in k['tsutae'])
        print('伝えたいことごとの型の数', dict(by.most_common()))
        json.dump(out, open(os.path.join(w, f'narabe-tameshi-{n}.json'), 'w'), ensure_ascii=False, indent=0)
        return
    daihon = json.load(open(sys.argv[2]))
    aida = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    out = narabe(w, daihon, aida)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(kazoe(out, aida), file=sys.stderr)


if __name__ == '__main__':
    main()
