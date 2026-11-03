#!/usr/bin/env python3
"""1周（10枚ほど）を回す：作り直し → 両方の画像 → 差を数える → kekka.json に足す。

使い方  python3 shuu.py <作業フォルダ> <周の名前> <ページ番号 ...> [--group] [--nobuild（作り直しを飛ばして画像と差だけ）]
  作業フォルダ … sou/ pptx/x/ppt/media/ tehon-img/ pres.json がある所（SLIDE_WORK）
  出す物 …… <周>/img/pNNN.png（作り直しの画像）・<周>/cmp/pNNN.jpg（並べた画像）・kekka.json（全周の数字）
作り直し先の資料は毎周、中身を全部消してから作る（URL は変わらない）
"""
import json, os, sys, subprocess

D = os.path.dirname(os.path.abspath(__file__))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    flags = [x for x in sys.argv[1:] if x.startswith('--')]
    w, name, pages = a[0], a[1], [int(x) for x in a[2:]]
    suji = os.environ.get('SLIDE_SUJI', '')   # 2本で回すときの筋（作り直し先の資料と結果の置き場を分ける）
    pid = json.load(open(os.path.join(w, f'pres{suji}.json')))['presentation']
    py = sys.executable
    if '--nobuild' not in flags:
        subprocess.run([py, os.path.join(D, 'fukusei.py'), 'build', pid, os.path.join(w, 'sou'), os.path.join(w, 'pptx/x/ppt/media')] + [str(p) for p in pages] + [f for f in flags if f != '--nobuild'], check=True)
    img = os.path.join(w, name, 'img')
    tmp = os.path.join(w, name, 'tmp')
    subprocess.run([py, os.path.join(D, 'sa.py'), 'thumbs', pid, tmp] + [str(i) for i in range(1, len(pages) + 1)], check=True)
    os.makedirs(img, exist_ok=True)
    for i, p in enumerate(pages, 1):
        os.replace(os.path.join(tmp, f'p{i:03d}.png'), os.path.join(img, f'p{p:03d}.png'))
    subprocess.run([py, os.path.join(D, 'sa.py'), 'thumbs', 'tehon', os.path.join(w, 'tehon-img')] + [str(p) for p in pages], check=True)
    subprocess.run([py, os.path.join(D, 'sa.py'), 'diff', os.path.join(w, 'tehon-img'), img, os.path.join(w, name, 'cmp')] + [f'{p}:{p}' for p in pages], check=True)
    kf = os.path.join(w, f'kekka{suji}.json')
    k = json.load(open(kf)) if os.path.exists(kf) else {}
    k[name] = json.load(open(os.path.join(w, name, 'cmp', 'diff.json')))
    json.dump(k, open(kf, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
