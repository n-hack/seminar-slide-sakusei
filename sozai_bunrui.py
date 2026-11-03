#!/usr/bin/env python3
"""手本の画像（pptx/x/ppt/media/）を6種類に分けて sozai/bunrui.json（ファイル名 → 種類）を作る。
mokuroku.py・kata_zenbu.py・kata_waku.py・orijinaru.py・kensa_ori.py がこの表を読む。

使い方  python3 sozai_bunrui.py <作業フォルダ>
  読む  sou/pNNN.json（その画像がページのどこに・どの大きさで置かれたか）・pptx/x/ppt/media/
  出す  sozai/bunrui.json

分け方（置かれた場所と、画像の透けと色の数で決める・境目はおおよそ。違う物は表を手で直す）
  867ページの手本で人が見て直した表と比べると 1578個中 1210個（77%）が同じ。外れの多くは線画アイコンとイラストの境目
  背景（全面）                       … ページの大部分（幅600pt以上かつ高さ330pt以上）に置かれた
  帯・線                             … 横に細長い（幅÷高さが25以上）
  線画アイコン・記号（透過・少色）     … 透ける画像で、色の数が少ない
  イラスト・人物・キャラ（透過・多色） … 透ける画像で、色の数が多い
  単色の板・図形                     … 透けない画像で、色の数がとても少ない
  写真・サムネ・画面の切り抜き         … 透けない画像で、色の数が多い
  壊れ                               … 開けなかった
"""
import collections, glob, json, os, sys
from PIL import Image

SUKUNAI = 16      # 透ける画像でこの色数以下なら線画アイコン（色は 32 段に丸めて数える）
OBI = 25          # 幅÷高さがこれ以上なら帯・線
ZENMEN = (600, 330)   # 置かれた大きさがこれ以上なら背景（全面）（ページは 720×405pt）
TANSHOKU = 4      # 透けない画像でこの色数以下なら単色の板


def iro_no_kazu(im):
    im = im.convert('RGBA')
    im.thumbnail((128, 128))
    px = im.tobytes()
    c = collections.Counter((r >> 3, g >> 3, b >> 3) for r, g, b, a in zip(px[0::4], px[1::4], px[2::4], px[3::4]) if a > 128)
    tot = sum(c.values()) or 1
    return sum(1 for n in c.values() if n / tot >= 0.005), im   # 0.5% 未満のふちの色は数えない


def sukeru(im):
    if im.mode not in ('RGBA', 'LA', 'P'):
        return False
    a = im.convert('RGBA').getchannel('A')
    return a.getextrema()[0] < 250


def main():
    w = sys.argv[1]
    media = os.path.join(w, 'pptx', 'x', 'ppt', 'media')
    oki = collections.defaultdict(list)   # 画像の名前 → 置かれた (幅, 高さ)
    for f in sorted(glob.glob(os.path.join(w, 'sou', 'p*.json'))):
        for L in json.load(open(f))['layers']:
            m = (L.get('fill') or {}).get('media')
            if m:
                oki[m].append((L['box'][2], L['box'][3]))
    out = {}
    for path in sorted(glob.glob(os.path.join(media, '*'))):
        name = os.path.basename(path)
        bx = collections.Counter((round(a), round(b)) for a, b in oki.get(name, [])).most_common(1)
        bw, bh = bx[0][0] if bx else (0, 0)
        try:
            im = Image.open(path)
            im.load()
        except Exception:
            out[name] = '壊れ'
            continue
        if bw >= ZENMEN[0] and bh >= ZENMEN[1]:
            out[name] = '背景（全面）'
            continue
        if bh and bw / bh >= OBI:
            out[name] = '帯・線'
            continue
        n, _ = iro_no_kazu(im)
        if sukeru(im):
            out[name] = '線画アイコン・記号（透過・少色）' if n <= SUKUNAI else 'イラスト・人物・キャラ（透過・多色）'
        else:
            out[name] = '単色の板・図形' if n <= TANSHOKU else '写真・サムネ・画面の切り抜き'
    os.makedirs(os.path.join(w, 'sozai'), exist_ok=True)
    json.dump(out, open(os.path.join(w, 'sozai', 'bunrui.json'), 'w'), ensure_ascii=False, indent=0)
    print(len(out), '個', dict(collections.Counter(out.values())))


if __name__ == '__main__':
    main()
