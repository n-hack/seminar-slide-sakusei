#!/usr/bin/env python3
"""層の記録（sou/）から「型の目録」kata.md と kata-index.json を作る。

使い方  python3 mokuroku.py <作業フォルダ>
  読む  sou/pNNN.json ・ sozai/bunrui.json（素材の自動分類）・ kata-types.json（型の名前と見本ページ・人が決めたもの）
  出す  kata.md（人が読む目録）・ kata-index.json（ページ→型・型→ページ）
型の決め方
  kata-types.json の各型に「見本ページ」を数枚書く。ほかのページは、層の作り（どの種類の層が・どの場所に・何枚）の
  近さで一番近い型に入れる（近さが足りなければ「その他」）
"""
import json, os, sys, glob, collections, math

SIKII = float(os.environ.get('KATA_SIKII', '0.25'))   # 型に入れる近さの下限（0〜1）
KIND_JA = {'blip': '画像の塗り', 'pic': '画像', 'vec': '自由な形', 'shape': '形', 'text': '文字', 'line': '線', 'video': '動画', 'group': '束ね'}


def feat(p, cat):
    """ページの作りを 6×4 のます目 × 層の種類 の数にした目印"""
    v = collections.Counter()
    for L in p['layers']:
        if L['kind'] == 'group':
            continue
        x, y, w, h = L['box']
        if w >= 700 and h >= 390:
            continue
        m = (L.get('fill') or {}).get('media')
        k = L['kind']
        if m:
            c = cat.get(m, '')
            k = 'ill' if 'イラスト' in c else 'icon' if 'アイコン' in c else 'photo' if '写真' in c else 'band' if '帯' in c else 'img'
        if k == 'text':
            big = max((r['size'] or 0) for r in L['text']['runs']) if L['text']['runs'] else 0
            k = 'text_big' if big >= 28 else 'text'
        cx, cy = min(5, max(0, int((x + w / 2) / 120))), min(3, max(0, int((y + h / 2) / 101.25)))
        v[(k, cx, cy)] += 1
    return v


def sim(a, b):
    keys = set(a) | set(b)
    num = sum(min(a[k], b[k]) for k in keys)
    den = sum(max(a[k], b[k]) for k in keys) or 1
    return num / den


def stack(p, cat):
    """1ページの層を下から順に1行ずつ（寸法・色つき）"""
    out = []
    for L in p['layers']:
        if L['kind'] == 'group':
            out.append(f"{'  ' * L['depth']}- 束ね（中に {len(L['children'])} 層）")
            continue
        x, y, w, h = (round(v) for v in L['box'])
        f = L.get('fill') or {}
        desc = KIND_JA.get(L['kind'], L['kind'])
        if f.get('media'):
            desc += f"：{cat.get(f['media'], '')}（{f['media']}）"
        elif f.get('type') == 'solid':
            desc += f"：塗り {f['color']}" + (f" 透明度{round((1 - f.get('alpha', 1)) * 100)}%" if f.get('alpha', 1) < 1 else '')
        elif f.get('type') == 'grad':
            desc += '：グラデ ' + '→'.join(s['color'] for s in f['stops']) + (f" {round(f.get('angle', 0))}°" if 'angle' in f else f" {f.get('path')}")
        if L.get('outline'):
            o = L['outline']
            desc += f" ／枠 {o['color']} {round(o['w'], 1)}pt"
        if L.get('text'):
            rs = [r for r in L['text']['runs'] if r['text'].strip()]
            szs = sorted({round(r['size'] or 0) for r in rs})
            cols = sorted({r['color'] for r in rs if r['color']})
            al = (L['text']['paras'][0].get('align') if L['text']['paras'] else '') or ''
            ls = (L['text']['paras'][0].get('lineSpacing') if L['text']['paras'] else None)
            t = L['text']['content'].replace('\n', '／').strip('／')[:28]
            desc += f"「{t}」 {'/'.join(map(str, szs))}pt {'・'.join(cols)} {'太' if any(r['bold'] for r in rs) else '細'} {al} 行間{round(ls) if ls else '-'}%"
        out.append(f"{'  ' * L['depth']}- z{L['z']} {desc} @ x{x} y{y} 幅{w} 高{h}")
    return out


def main():
    w = sys.argv[1]
    cat = json.load(open(os.path.join(w, 'sozai', 'bunrui.json')))
    types = json.load(open(os.path.join(w, 'kata-types.json')))
    pages = {int(os.path.basename(f)[1:4]): json.load(open(f)) for f in glob.glob(os.path.join(w, 'sou', 'p*.json'))}
    F = {n: feat(p, cat) for n, p in pages.items()}
    assign, score = {}, {}
    for n in pages:
        best = (0, 'その他')
        for t in types:
            s = max(sim(F[n], F[r]) for r in t['pages'])
            best = max(best, (s, t['name']))
        assign[n] = best[1] if best[0] >= SIKII else 'その他'
        score[n] = round(best[0], 2)
    by = collections.defaultdict(list)
    for n, t in assign.items():
        by[t].append(n)
    # 色・字の一覧
    colC, fontC, sizeC, fillC = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    for p in pages.values():
        for L in p['layers']:
            for r in (L.get('text') or {}).get('runs', []):
                if r['text'].strip():
                    colC[r['color']] += len(r['text'].strip())
                    fontC[f"{r['font']} {r['weight']}"] += len(r['text'].strip())
                    sizeC[round(r['size'] or 0)] += 1
            f = L.get('fill') or {}
            if f.get('type') == 'solid':
                fillC[f['color']] += 1
            elif f.get('type') == 'grad':
                fillC['グラデ ' + '→'.join(s['color'] for s in f['stops'])] += 1
    md = ['# 型の目録（手本のスライド・自動で作った表＋人が名前をつけた型）', '',
          '作り：`python3 mokuroku.py <作業フォルダ>`（kata-types.json を直して作り直す）', '',
          '## 全ページ共通の枠（ほぼ全部のページに同じ層が同じ場所にある）', '']
    common = collections.Counter()
    for p in pages.values():
        seen = set()
        for L in p['layers']:
            m = (L.get('fill') or {}).get('media')
            if m and m not in seen:
                seen.add(m)
                common[(m, tuple(round(v) for v in L['box']))] += 1
    for (m, b), c in common.most_common(8):
        md.append(f'- {c}ページ：{cat.get(m, "")} {m} @ x{b[0]} y{b[1]} 幅{b[2]} 高{b[3]}')
    md += ['', '## 字（使った文字数の多い順）', '']
    md += [f'- {k}：{v}字' for k, v in fontC.most_common(6)]
    md += ['', '## 字の色（文字数）', '']
    md += [f'- {k}：{v}字' for k, v in colC.most_common(15)]
    md += ['', '## 字の大きさ（文字の箱の数）', '', '- ' + '、'.join(f'{k}pt×{v}' for k, v in sorted(sizeC.items(), key=lambda x: -x[1])[:20])]
    md += ['', '## 形の塗り（回数）', '']
    md += [f'- {k}：{v}' for k, v in fillC.most_common(15)]
    md += ['', '## 型（ページ数の多い順）', '']
    for t in sorted(types, key=lambda t: -len(by.get(t['name'], []))):
        ps = sorted(by.get(t['name'], []))
        md += [f"### {t['name']}（{len(ps)}ページ）", '', t.get('setsumei', ''), '',
               f"- 見本：{', '.join(f'p{x}' for x in t['pages'])}",
               f"- 入っているページ（先頭20）：{', '.join(map(str, ps[:20]))}",
               f"- 使いどころ：{t.get('tsukaidokoro', '')}", '', f"見本 p{t['pages'][0]} の層（下から）", '']
        md += stack(pages[t['pages'][0]], cat)
        md.append('')
    md += [f"### その他（{len(by.get('その他', []))}ページ）", '', '- ' + ', '.join(map(str, sorted(by.get('その他', []))[:60]))]
    open(os.path.join(w, 'kata.md'), 'w').write('\n'.join(md) + '\n')
    json.dump({'page2kata': assign, 'score': score, 'kata2pages': {k: sorted(v) for k, v in by.items()}},
              open(os.path.join(w, 'kata-index.json'), 'w'), ensure_ascii=False, indent=0)
    print({k: len(v) for k, v in sorted(by.items(), key=lambda x: -len(x[1]))})


if __name__ == '__main__':
    main()
