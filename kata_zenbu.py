#!/usr/bin/env python3
"""手本の全ページを1枚ずつ別の型として残す（まとめない）。伝えたいこと・連番の組・似せて続ける組も記録する。

使い方  python3 kata_zenbu.py <作業フォルダ>
  読む  sou/pNNN.json（層）・kata-index.json（大きな型）・sozai/bunrui.json（素材の分類）
  出す  kata-zenbu.json（型の本体）・kata-zenbu.md（人が読む一覧と数え）
型の中身（1ページ＝1型 K001〜）
  ookii   大きな型（mokuroku.py の A〜J・その他）
  kouzou  層の並び（種類・置き場所 720×405 の pt・素材の分類・文字の大きさと字数）。作るときはこの並びに新しい文言と素材を入れる
  moji    手本の文言（読むための控え。そのまま使わない）
  tsutae  そのページが何を伝えるための形か（決まりで付ける・1つ目が主）
  renban  1つずつ足していく連番の組の番号（無ければ null）・何枚目か
  nitsuzuke  わざと似た形を続ける組の番号
連番の決め方   前のページの層が全部そのまま残り、層が増えている（場所・種類・素材・文言が同じ）
似せて続ける   層の種類と場所が同じか、大きな型が同じで、文言か素材だけが違うページが続く（連番の組の中は除く）
"""
import json, os, re, sys, glob, collections

TSUTAE = [  # (名前, 文言の目印, 形の目印)
    ('問いかけて考えさせる', r'[？?]|質問|どう思|ですか|ませんか', None),
    ('数字で驚かせる', r'[0-9０-９]+\s*(万|億|円|%|％|倍|人|件|日|時間|分|社|本)', 'big_num'),
    ('比べて差を見せる', r'昔|今は|これまで|これから|ビフォー|アフター|比較|vs|VS|✕|×|違い|より', 'two_col'),
    ('手順を見せる', r'STEP|ステップ|手順|まず|次に|最後に|①|②|③|1\.|2\.', 'flow'),
    ('全体を一覧で見せる', None, 'cards'),
    ('不安をあおる', r'不安|損|危険|止ま|失|やばい|リスク|手遅れ|知らない|取り残|間に合わ|消え', None),
    ('悩みを代弁して共感させる', r'悩|困|大変|つら|しんど|できない|わからない|分からない|時間がない', None),
    ('結論を言い切る', r'結論|つまり|正直|言います|断言|答えは|です！|します！', None),
    ('実績で信じさせる', r'実績|達成|月収|年収|売上|成果|突破|万円|稼', 'photo'),
    ('未来を見せて期待を上げる', r'未来|できる|なれる|可能|自由|叶|手に入|変わ', None),
    ('特典・行動を促す', r'特典|プレゼント|今すぐ|申込|申し込|LINE|限定|無料|登録|受け取', None),
    ('章を区切る', r'第[0-9０-９一二三四五六七八九十]+|章|Part|PART|パート', 'title_only'),
    ('キャラに語らせて親しみを出す', None, 'chara'),
    ('人物の表情で気持ちを見せる', None, 'person'),
]


def load(w):
    pages = {}
    for f in sorted(glob.glob(os.path.join(w, 'sou', 'p[0-9][0-9][0-9].json'))):
        n = int(os.path.basename(f)[1:4])
        pages[n] = json.load(open(f))
    return pages


def layers(pg, cat):
    out = []
    for L in pg['layers']:
        if L['kind'] == 'group':
            continue
        x, y, w, h = L['box']
        m = (L.get('fill') or {}).get('media')
        t = (L.get('text') or {}).get('content', '').strip()
        sz = max([r.get('size') or 0 for r in (L.get('text') or {}).get('runs', []) if r['text'].strip()] or [0])
        out.append({'kind': L['kind'], 'box': [round(x), round(y), round(w), round(h)], 'media': m,
                    'sozai': cat.get(m, '') if m else '', 'moji': t, 'size': round(sz, 1), 'jisuu': len(t)})
    return out


def sig_full(l):   # 連番：同じ層かどうか
    b = tuple(v // 4 for v in l['box'])
    return (l['kind'], b, l['media'] or '', l['moji'])


def sig_kata(l):   # 似せて続ける：場所と種類だけ（文字の箱は字数で大きさが変わるので左上だけ見る）
    x, y, w, h = l['box']
    if l['moji']:
        return ('text', x // 24, y // 24)
    return (l['kind'], x // 24, y // 24, w // 48, h // 48, l['sozai'])


def katachi(ls, ookii):
    s = set()
    big = [l for l in ls if l['moji'] and l['size'] >= 40 and re.search(r'[0-9０-９]', l['moji'])]
    if big:
        s.add('big_num')
    texts = [l for l in ls if l['moji']]
    if len(texts) >= 2 and any(l['box'][0] < 300 for l in texts) and any(l['box'][0] > 380 for l in texts) and ookii.startswith('J'):
        s.add('two_col')
    if ookii.startswith('G') or ookii.startswith('A'):
        s.add('flow')
    if ookii.startswith('F'):
        s.add('cards')
    if ookii.startswith('I'):
        s.add('chara')
    if ookii.startswith(('B', 'C')):
        s.add('person')
    if any('写真' in l['sozai'] for l in ls):
        s.add('photo')
    if len(texts) == 1 and texts[0]['jisuu'] <= 25:
        s.add('title_only')
    return s


def tsutae_of(ls, ookii):
    moji = '\n'.join(l['moji'] for l in ls if l['moji'])
    k = katachi(ls, ookii)
    sc = []
    for name, rx, kk in TSUTAE:
        v = 0
        if rx and re.search(rx, moji):
            v += len(re.findall(rx, moji))
        if kk and kk in k:
            v += 2
        if v:
            sc.append((v, name))
    sc.sort(key=lambda x: -x[0])
    return [n for _, n in sc] or ['説明する']


def main():
    w = sys.argv[1]
    pages = load(w)
    cat = json.load(open(os.path.join(w, 'sozai', 'bunrui.json')))
    p2k = json.load(open(os.path.join(w, 'kata-index.json')))['page2kata']
    ls = {n: layers(pg, cat) for n, pg in pages.items()}
    kata = {}
    for n in sorted(pages):
        ookii = p2k.get(str(n), 'その他')
        kata[n] = {'id': f'K{n:03d}', 'page': n, 'ookii': ookii, 'kouzou': ls[n],
                   'moji': [l['moji'] for l in ls[n] if l['moji']], 'tsutae': tsutae_of(ls[n], ookii),
                   'renban': None, 'renban_no': None, 'nitsuzuke': None}
    # 連番：前のページの層が全部残って層が増える
    gid = 0
    ns = sorted(pages)
    for a, b in zip(ns, ns[1:]):
        if b != a + 1:
            continue
        A = collections.Counter(sig_full(l) for l in ls[a])
        B = collections.Counter(sig_full(l) for l in ls[b])
        if len(ls[b]) > len(ls[a]) and not (A - B) and len(ls[a]) >= 2:
            if kata[a]['renban'] is None:
                gid += 1
                kata[a]['renban'], kata[a]['renban_no'] = gid, 1
            kata[b]['renban'], kata[b]['renban_no'] = kata[a]['renban'], kata[a]['renban_no'] + 1
    # 似せて続ける：場所と種類が同じで文言か素材が違う（連番でないもの）
    nid = 0
    for a, b in zip(ns, ns[1:]):
        if b != a + 1 or (kata[b]['renban'] and kata[b]['renban'] == kata[a]['renban']):
            continue
        A = sorted(sig_kata(l) for l in ls[a])
        B = sorted(sig_kata(l) for l in ls[b])
        onaji = kata[a]['ookii'] == kata[b]['ookii'] and kata[a]['ookii'] != 'その他'   # 同じ大きな型が続く（手本で104か所）
        if (A == B or onaji) and len(A) >= 2 and [l['moji'] for l in ls[a]] != [l['moji'] for l in ls[b]]:
            if kata[a]['nitsuzuke'] is None:
                nid += 1
                kata[a]['nitsuzuke'] = nid
            kata[b]['nitsuzuke'] = kata[a]['nitsuzuke']
    json.dump({'kata': list(kata.values())}, open(os.path.join(w, 'kata-zenbu.json'), 'w'), ensure_ascii=False, indent=1)
    # 数え
    tsu = collections.Counter(k['tsutae'][0] for k in kata.values())
    tsu_all = collections.Counter(t for k in kata.values() for t in k['tsutae'])
    rb = collections.defaultdict(list)
    for k in kata.values():
        if k['renban']:
            rb[k['renban']].append(k['page'])
    nt = collections.defaultdict(list)
    for k in kata.values():
        if k['nitsuzuke']:
            nt[k['nitsuzuke']].append(k['page'])
    md = ['# 型の目録（全ページ・1ページ＝1型）', '',
          f'- 型の数：{len(kata)}（大きな型 {len(set(p2k.values()))} 種の中に入れて持つ）',
          f'- 伝えたいことの種類：{len(tsu_all)}（主に付いたもの {len(tsu)} 種）',
          f'- 連番の組（1つずつ足す）：{len(rb)} 組・{sum(len(v) for v in rb.values())} 枚',
          f'- 似せて続ける組：{len(nt)} 組・{sum(len(v) for v in nt.values())} 枚', '',
          '## 伝えたいこと（主）の数', ''] + [f'- {k}：{v}' for k, v in tsu.most_common()] + \
         ['', '## 伝えたいこと（付いた数・1ページに複数）', ''] + [f'- {k}：{v}' for k, v in tsu_all.most_common()] + \
         ['', '## 連番の組', ''] + [f'- 組{g}：p' + '→'.join(map(str, v)) for g, v in sorted(rb.items())] + \
         ['', '## 似せて続ける組', ''] + [f'- 組{g}：p' + '→'.join(map(str, v)) for g, v in sorted(nt.items())] + \
         ['', '## 型の一覧（ページ・大きな型・伝えたいこと・最初の文言）', ''] + \
         [f'- {k["id"]}　{k["ookii"]}　{"・".join(k["tsutae"][:3])}　{(k["moji"][0] if k["moji"] else "").splitlines()[0][:30] if k["moji"] else ""}' for k in kata.values()]
    open(os.path.join(w, 'kata-zenbu.md'), 'w').write('\n'.join(md) + '\n')
    print(f'型 {len(kata)}・伝えたいこと {len(tsu_all)} 種（主 {len(tsu)}）・連番 {len(rb)} 組 {sum(len(v) for v in rb.values())} 枚・似せて続ける {len(nt)} 組')


if __name__ == '__main__':
    main()
