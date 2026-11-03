#!/usr/bin/env python3
"""まだ作り直していないページを 1周10枚ずつ全部回す（shuu.py を順に呼ぶ）。

使い方  nice -n 19 python3 zenbu.py <作業フォルダ> [1周の枚数=10]
決まり
  ・周を始める前にメモリの圧力を見る（1＝通常 以外なら 60秒ごとに待つ）
  ・周が失敗したら同じ周を2回までやり直す。それでもだめなら「作れず」に記録して次へ
  ・合格の線＝違う所 3% 以下 かつ ssim 0.985 以上
  ・同じ型で3周続けて合格の線を割ったら止める（zenbu-stop.txt に理由）
  ・100枚ごとに zenbu-100/NNN.txt を置く（報告の合図）
  ・止めるときは作業フォルダに zenbu-tomeru を置く（周の間で止まる。kill すると一時公開が残る）
  ・作れなかったページは最後に1回だけ回し直す
記録  zenbu.log（周ごとの1行）・kekka.json（shuu.py が足す）・zenbu-tsukurezu.json
"""
import json, os, sys, subprocess, time

D = os.path.dirname(os.path.abspath(__file__))
RATIO_MAX, SSIM_MIN = 3.0, 0.985


def atsu():
    try:
        return int(subprocess.check_output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level']).strip())
    except Exception:
        return 1


def main():
    w = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    # 2本で回すとき：SLIDE_SUJI（例 -b）と受け持ちのページ（始め 終わり）を分ける。済みは全部の kekka*.json を合わせて数える
    suji = os.environ.get('SLIDE_SUJI', '')
    kf = os.path.join(w, f'kekka{suji}.json')
    kata = json.load(open(os.path.join(w, 'kata-index.json')))['page2kata']
    total = len([f for f in os.listdir(os.path.join(w, 'sou')) if f.startswith('p') and f[1:4].isdigit() and len(f) == 9])
    hajime = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    owari = int(sys.argv[4]) if len(sys.argv) > 4 else total
    tf = os.path.join(w, f'zenbu-tsukurezu{suji}.json')
    tsukurezu = json.load(open(tf)) if os.path.exists(tf) else []
    log = open(os.path.join(w, f'zenbu{suji}.log'), 'a')
    os.makedirs(os.path.join(w, 'zenbu-100'), exist_ok=True)
    streak = {}                         # 型 → 続けて割った周の数
    retried = False
    while True:
        import glob
        done = set()
        for f in glob.glob(os.path.join(w, 'kekka*.json')):
            done |= {int(p) for r in json.load(open(f)).values() for p in r}
        todo = [p for p in range(hajime, owari + 1) if p not in done and p not in tsukurezu]
        if not todo and tsukurezu and not retried:
            # 作れなかったページは最後にもう1回だけ回す（11/01 z041・z054 は1枚ずつなら全部作れた＝一時の失敗）
            retried = True
            log.write(f'{time.strftime("%H:%M")} 作れなかった {len(tsukurezu)} 枚をもう1回\n'); log.flush()
            tsukurezu = []
            json.dump(tsukurezu, open(tf, 'w'))
            continue
        if not todo:
            log.write(f'{time.strftime("%H:%M")} 全部終わり\n'); log.flush()
            break
        pages = todo[:n]
        # 止めるときは zenbu-tomeru を置く（周の途中で殺すと素材の一時公開が残る・11/01 21:1x に1件残った）
        if os.path.exists(os.path.join(w, 'zenbu-tomeru')):
            log.write(f'{time.strftime("%H:%M")} zenbu-tomeru で止めた\n'); log.flush()
            break
        while atsu() != 1:
            time.sleep(60)
        name = f'z{pages[0]:03d}'
        ok = False
        for t in range(3):
            # やり直しても前の回の記録を消さない（1回目の本当の原因が残るように・11/01 z041 で消えた）
            lf = open(os.path.join(w, f'{name}.log'), 'a')
            lf.write(f'--- {time.strftime("%H:%M:%S")} {t + 1}回目\n'); lf.flush()
            r = subprocess.run([sys.executable, os.path.join(D, 'shuu.py'), w, name] + [str(p) for p in pages],
                               stdout=lf, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                ok = True
                break
            time.sleep(30 * (t + 1))
        if not ok:
            tsukurezu += pages
            json.dump(tsukurezu, open(tf, 'w'))
            log.write(f'{time.strftime("%H:%M")} {name} 作れず {pages}\n'); log.flush()
            continue
        res = json.load(open(kf))[name]
        bad = {p: v for p, v in res.items() if not (v['ratio'] <= RATIO_MAX and v['ssim'] >= SSIM_MIN)}
        badk = {kata.get(str(p), 'その他') for p in bad}
        for kk in list(streak):
            if kk not in badk:
                streak[kk] = 0
        for kk in badk:
            streak[kk] = streak.get(kk, 0) + 1
        rs = [v['ratio'] for v in res.values()]
        log.write(f'{time.strftime("%H:%M")} {name} {len(res)}枚 合格{len(res) - len(bad)} 平均{sum(rs) / len(rs):.2f} 最大{max(rs)} 割った{sorted(bad)}\n')
        log.flush()
        ndone = len(done) + len(res)
        for m in range(100, ndone + 1, 100):
            f = os.path.join(w, 'zenbu-100', f'{m:04d}.txt')
            if not os.path.exists(f):
                open(f, 'w').write(f'{ndone}枚 {time.strftime("%m/%d %H:%M")}\n')
        stop = [kk for kk, v in streak.items() if v >= 3]
        if stop:
            open(os.path.join(w, f'zenbu-stop{suji}.txt'), 'w').write(f'同じ型で3周続けて割った：{stop}（最後の周 {name}）\n')
            log.write(f'{time.strftime("%H:%M")} 止めた {stop}\n'); log.flush()
            break


if __name__ == '__main__':
    main()
