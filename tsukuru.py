#!/usr/bin/env python3
"""一言の頼み（テーマ・相手・枚数）から新しいスライドを作る入口。型選び→文字数の門→作る→画像→門→URL を1本で回す。

台本の中身（伝えたいことの並び・各ページの文）は AI（Claude など）か人が手で書く。
型の選び方・箱ごとの文字数の上限・人物とアイコンの選び方は、この道具と表（kata-waku.json）で決める。

使い方（作業フォルダ W=$SLIDE_WORK・出す先 OUT は頼みごとに新しく）
  python3 tsukuru.py erabu  <W> <OUT>          OUT/kousei.json（伝えたいことの並び）から型を選び、
                                               OUT/waku.md（箱ごとの上限と手本の文）と OUT/daihon.json のひな形を作る
  python3 tsukuru.py mon    <W> <OUT>          OUT/daihon.json を箱の上限で調べる（不合格なら 1 で終わる）
  python3 tsukuru.py tsukuru <W> <OUT> [--pres <試し用の資料ID>]
                                               門→orijinaru.py→fukusei.py build→画像→kensa_ori.py→並べた画像→
                                               枚数を API で数える。全部合格のときだけ URL を出す（OUT/kekka.json）
kousei.json … {"irai": "一言の頼み", "aite": "相手", "pages": [{"tsutae": "問いかけて考えさせる", "memo": "このページで言うこと",
               "hito": true, "icon": 0, "hako": 2}, ...]}
     tsutae … 伝えたいこと15種（python3 tsukuru.py tsutae <W> で一覧）
     hito   … 人物の絵が要るか（true／false・省くとどちらでも）  icon … アイコンの数（省くとどちらでも）
     hako   … 文字の箱の数（省くと 1〜6）  kata … 型を直に指すとき（例 "K048"）
daihon.json … erabu が作るひな形の moji を埋める。hito・icon は "auto" なら表で決める（make.py の HITO_WORDS・ICON_WORDS）
決まり
  ・使う型は「手本の作り直しが合格」かつ「写真・画面・動画なし」の770型だけ（kata-waku.md）
  ・前の2枚と同じ大きな型は選ばない／同じ型は使い回さない
  ・箱ごとに 行数 ≤ 手本の行数（gyou）・1行の字数 ≤ per。越えたら作らない（11/01 仕事1：1行の箱に2行入れてアイコンに重なった）
  ・build は同時に1本・nice -n 19・メモリの圧力が1のときだけ始める・最後に「公開の残り 0 件」を確かめる
  ・手本と本番用の資料には書き込まない（作る先は試し用の資料か、新しく作る資料だけ）
"""
import json, os, sys, math, re, subprocess, time, collections, glob

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

AIDA = 2          # 前の何枚に同じ大きな型があれば避けるか
HAKO_MAX = 6      # 箱の数を指定しないときの上限（多すぎる型は文が細切れになる）
HITO_TSUTAE = {'不安をあおる': '悩む', '悩みを代弁して共感させる': '悩む', '問いかけて考えさせる': '考える',
               '実績で信じさせる': '成功', '未来を見せて期待を上げる': '成功', '特典・行動を促す': '贈り物',
               '数字で驚かせる': 'グラフ', '手順を見せる': 'PC', '説明する': '説明', '結論を言い切る': '説明'}


def atsu():
    try:
        return int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level']).strip())
    except Exception:
        return 1


def waku_hyou(w):
    K = json.load(open(os.path.join(w, 'kata-waku.json')))['kata']
    return [k for k in K if k['goukaku'] and not k['dame']], {k['id']: k for k in K}


def sabun(w):
    """手本の作り直しの違う所（ratio）。小さいほど作り直しが手本に近い＝同じ質で作れる"""
    best = {}
    for f in sorted(glob.glob(os.path.join(w, 'kekka*.json'))):
        for _, d in json.load(open(f)).items():
            for p, v in d.items():
                best[int(p)] = min(best.get(int(p), 99), v['ratio'])
    return best


def hito_ok(page, _c={}):
    """その手本のページで差し替えられる人物の絵の数（assets/hito_sashikae.json の ok にある絵だけ）"""
    if 'ok' not in _c:
        _c['ok'] = set(json.load(open(os.path.join(D, 'assets', 'hito_sashikae.json')))['ok'])
        _c['w'] = None
    f = os.path.join(W_, 'sou', f'p{page:03d}.json')
    if not os.path.exists(f):   # 層の記録が無い作業フォルダ（型の表だけのとき）は表の人物の数で数える
        return next((k['hito'] for k in json.load(open(os.path.join(W_, 'kata-waku.json')))['kata'] if k['page'] == page), 0)
    pg = json.load(open(f))
    return sum(1 for L in pg['layers'] if (L.get('fill') or {}).get('media') in _c['ok'] and L['box'][3] > 60)


from settei import WORK as W_


def erabu(w, out):
    global W_
    W_ = w
    ks = json.load(open(os.path.join(out, 'kousei.json')))
    ok, by_id = waku_hyou(w)
    sa = sabun(w)
    used, res = collections.Counter(), []
    for i, pg in enumerate(ks['pages']):
        if pg.get('kata'):
            k = by_id[pg['kata']]
        else:
            t = pg['tsutae']
            mae = [r['ookii'] for r in res[-AIDA:]]

            def au(k, hikui=False):
                if t not in k['tsutae'] or used[k['id']]:
                    return False
                if 'hito' in pg and (hito_ok(k['page']) > 0) != bool(pg['hito']):
                    return False
                if 'icon' in pg and k['icon'] != pg['icon']:
                    return False
                n = len(k['hako'])
                if ('hako' in pg and n != pg['hako']) or not 1 <= n <= HAKO_MAX:
                    return False
                return hikui or k['ookii'] == 'その他' or k['ookii'] not in mae
            cand = [k for k in ok if au(k)] or [k for k in ok if au(k, True)]
            if not cand:
                sys.exit(f'{i + 1}枚目：「{t}」で条件に合う型が0（hito・icon・hako を外して erabu し直す）')
            # 大きな型（A〜J）がある型→伝えたいことが主（1つ目）に付いた型→作り直しが手本に近い型→番号の若い型（毎回同じ結果）
            # 「その他」は1枚だけの作りが多く、伝えたいことと見た目が合わないことがある（11/03 表題に「ご清聴ありがとう」の型）
            k = min(cand, key=lambda k: (k['ookii'] == 'その他', k['tsutae'][0] != t, sa.get(k['page'], 99), k['page']))
        used[k['id']] += 1
        res.append({'mai': i + 1, 'kata': k['id'], 'base': k['page'], 'ookii': k['ookii'], 'tsutae': pg.get('tsutae'),
                    'memo': pg.get('memo', ''), 'hito': hito_ok(k['page']), 'icon': k['icon'],
                    'hako': [{'per': h['per'], 'gyou': h['gyou'], 'size': h['size'], 'moto': h['moto']} for h in k['hako']]})
    json.dump(res, open(os.path.join(out, 'erabi.json'), 'w'), ensure_ascii=False, indent=1)
    with open(os.path.join(out, 'waku.md'), 'w') as f:
        f.write(f"# 型と箱の上限（tsukuru.py erabu・{ks.get('irai', '')}／相手 {ks.get('aite', '')}）\n\n")
        f.write('箱は上から順（同じ高さなら左から）。上限＝1行の字数 per × 行数 gyou。手本の文は字数と言い方の見本\n\n')
        for r in res:
            f.write(f"## {r['mai']}枚目 {r['kata']}（手本p{r['base']}・{r['ookii']}）{r['tsutae']}\n- 言うこと：{r['memo']}\n"
                    f"- 人物 {r['hito']}・アイコン {r['icon']}\n")
            for j, h in enumerate(r['hako']):
                f.write(f"  {j + 1}. {h['per']}字×{h['gyou']}行（{h['size']}pt）手本「{h['moto'].replace(chr(10), '／')}」\n")
            f.write('\n')
    hina = os.path.join(out, 'daihon.json')
    if not os.path.exists(hina):
        json.dump([{'kata': r['kata'], 'base': r['base'], 'moji': [''] * len(r['hako']),
                    **({'hito': 'auto'} if r['hito'] else {}), **({'icon': 'auto'} if r['icon'] else {})} for r in res],
                  open(hina, 'w'), ensure_ascii=False, indent=1)
    print(f"{len(res)}枚の型を選んだ → {out}/waku.md・daihon.json（使った大きな型 {dict(collections.Counter(r['ookii'] for r in res))}）")


def jisuu(s):
    """字数。半角（英数・記号）は0.5字で数える（「STEP 1」＝3字・手本の箱の幅に合わせる）"""
    from orijinaru import haba
    return haba(re.sub(r'\\?[【】]', '', s))


def mon(w, out, quiet=False):
    dh = json.load(open(os.path.join(out, 'daihon.json')))
    _, by_id = waku_hyou(w)
    fu = []
    for i, p in enumerate(dh):
        k = by_id[p['kata']]
        if len(p['moji']) > len(k['hako']):
            fu.append(f"{i + 1}枚目：文が{len(p['moji'])}個・箱は{len(k['hako'])}個")
        for j, (s, h) in enumerate(zip(p['moji'], k['hako'])):
            if not s.strip():
                fu.append(f"{i + 1}枚目 箱{j + 1}：空（手本「{h['moto'][:12]}」）")
                continue
            lines = s.split('\n')
            n = sum(max(1, math.ceil(jisuu(l) / h['per'])) for l in lines)
            if n > h['gyou']:
                fu.append(f"{i + 1}枚目 箱{j + 1}「{s[:12]}」：{n}行（上限 {h['gyou']}行×{h['per']}字）")
            elif any(jisuu(l) > h['per'] for l in lines) and h['gyou'] == 1:
                fu.append(f"{i + 1}枚目 箱{j + 1}「{s[:12]}」：1行{max(jisuu(l) for l in lines)}字（上限 {h['per']}字）")
    if not quiet:
        print('\n'.join(fu) if fu else f'文字数の門 合格（{len(dh)}枚）')
    return fu


def auto_e(w, dh):
    """hito・icon が "auto" のページを表で決める（make.py の言葉の表）"""
    import make
    from orijinaru import order, icon_slots
    for p in dh:
        sou = json.load(open(os.path.join(w, 'sou', f"p{p['base']:03d}.json")))
        zen = ' '.join(p['moji'])
        if p.get('hito') == 'auto':
            m = next((m for words, m in make.HITO_WORDS if any(x in zen for x in words)), None)
            p['hito'] = m or HITO_TSUTAE.get(p.get('tsutae', ''), '説明')
        if p.get('icon') == 'auto':
            cat = json.load(open(os.path.join(w, 'sozai', 'bunrui.json')))
            ic = icon_slots(sou['layers'], cat)
            slots = order(sou['layers'])
            names, tsukatta = [], set()
            for L in ic:
                cx, cy = L['box'][0] + L['box'][2] / 2, L['box'][1] + L['box'][3] / 2
                # 一番近い文字の箱の文（見出しより、アイコンのそばの文を優先）
                near = sorted(((abs(S['box'][0] + S['box'][2] / 2 - cx) + abs(S['box'][1] + S['box'][3] / 2 - cy), k)
                               for k, S in enumerate(slots) if k < len(p['moji'])))
                nm = None
                for _, k in near[:2]:
                    nm = next((n for words, n in make.ICON_WORDS if n not in tsukatta and any(x in p['moji'][k] for x in words)), None)
                    if nm:
                        break
                nm = nm or next(n for n in ('check_circle', 'star', 'task_alt', 'lightbulb', 'target') if n not in tsukatta)
                tsukatta.add(nm)
                names.append(nm)
            p['icon'] = names
    return dh


def run(cmd, log):
    with open(log, 'a') as f:
        f.write('$ ' + ' '.join(cmd) + '\n')
        f.flush()
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode


def kazoe_mai(pid):
    from sa import slides_ro
    return len(slides_ro().presentations().get(presentationId=pid, fields='slides.objectId').execute().get('slides', []))


def narabe_gazou(w, out, dh):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 640, 360
    rows = len(dh)
    im = Image.new('RGB', (W * 2 + 30, rows * (H + 34) + 10), 'white')
    dr = ImageDraw.Draw(im)
    f = ImageFont.truetype(__import__('settei').FONT, 20)
    for i, p in enumerate(dh):
        y = 10 + i * (H + 34)
        dr.text((10, y), f"{i + 1}枚目 {p['kata']}（左＝手本p{p['base']}・右＝今回）", fill='black', font=f)
        a = Image.open(os.path.join(w, 'tehon-img', f"p{p['base']:03d}.png")).convert('RGB').resize((W, H))
        b = Image.open(os.path.join(out, 'img', f'p{i + 1:03d}.png')).convert('RGB').resize((W, H))
        im.paste(a, (10, y + 28))
        im.paste(b, (W + 20, y + 28))
    im.save(os.path.join(out, 'narabe.jpg'), quality=85)


def tsukuru(w, out, pid=None):
    log = os.path.join(out, 'tsukuru.log')
    if mon(w, out):
        sys.exit('文字数の門で不合格 → daihon.json を直す（作らない）')
    dh = auto_e(w, json.load(open(os.path.join(out, 'daihon.json'))))
    json.dump(dh, open(os.path.join(out, 'daihon-kata.json'), 'w'), ensure_ascii=False, indent=1)
    if not pid:
        r = subprocess.run([sys.executable, os.path.join(D, 'fukusei.py'), 'new', f"オリジナル（{time.strftime('%m/%d %H:%M')}）"],
                           capture_output=True, text=True, check=True)
        pid = json.loads(r.stdout.strip().splitlines()[-1])['presentation']
    subprocess.run(['rm', '-rf', os.path.join(out, 'sou'), os.path.join(out, 'img')])
    if run([sys.executable, os.path.join(D, 'orijinaru.py'), w, os.path.join(out, 'daihon-kata.json'), out], log):
        sys.exit('orijinaru.py が失敗（tsukuru.log）')
    while atsu() != 1:
        print('メモリの圧力が1でないので待つ', flush=True)
        time.sleep(60)
    pages = [str(9001 + i) for i in range(len(dh))]
    for t in range(3):
        n0 = os.path.getsize(log)
        rc = run(['nice', '-n', '19', sys.executable, os.path.join(D, 'fukusei.py'), 'build', pid, os.path.join(out, 'sou'),
                  os.path.join(w, 'pptx', 'x', 'ppt', 'media')] + pages, log)
        tail = open(log).read()[n0:]
        nokori = re.findall(r'公開の残り (\d+) 件', tail)
        if nokori and nokori[-1] != '0':
            sys.exit(f'一時公開が {nokori[-1]} 件残った → fukusei.py の後始末を確かめる')
        if rc == 0:
            break
        print(f'build 失敗（{t + 1}回目）・やり直す', flush=True)
        time.sleep(20)
    else:
        sys.exit('build が3回失敗（tsukuru.log）')
    if run(['nice', '-n', '19', sys.executable, os.path.join(D, 'sa.py'), 'thumbs', pid, os.path.join(out, 'img')], log):
        sys.exit('画像が取れない（tsukuru.log）')
    rc = run([sys.executable, os.path.join(D, 'kensa_ori.py'), w, out], log)
    narabe_gazou(w, out, dh)
    kensa = json.load(open(os.path.join(out, 'kensa.json')))
    mai = kazoe_mai(pid)
    url = f'https://docs.google.com/presentation/d/{pid}/edit'
    kekka = {'presentation': pid, 'mai_api': mai, 'mai_daihon': len(dh), 'fugoukaku': kensa['fugoukaku'],
             'url': url if (rc == 0 and mai == len(dh)) else None}
    json.dump(kekka, open(os.path.join(out, 'kekka.json'), 'w'), ensure_ascii=False, indent=1)
    for p in kensa['pages']:
        print(f"{p['mai']:2d}枚目 手本p{p['base']} {'合格' if p['goukaku'] else '不合格 ' + ' ／ '.join(p['fugoukaku'])}")
    print(f"枚数 API {mai}／台本 {len(dh)}・不合格 {kensa['fugoukaku']}枚 → " + (f'URL {url}' if kekka['url'] else 'URL は出さない（直してから tsukuru し直す）'))
    sys.exit(0 if kekka['url'] else 1)


def main():
    a = sys.argv[1:]
    if a[0] == 'tsutae':
        ok, _ = waku_hyou(a[1])
        for t, n in collections.Counter(t for k in ok for t in k['tsutae']).most_common():
            print(f'{t}\t{n}型')
    elif a[0] == 'erabu':
        erabu(a[1], a[2])
    elif a[0] == 'mon':
        sys.exit(1 if mon(a[1], a[2]) else 0)
    elif a[0] == 'tsukuru':
        pid = a[a.index('--pres') + 1] if '--pres' in a else None
        tsukuru(a[1], a[2], pid)


if __name__ == '__main__':
    main()
