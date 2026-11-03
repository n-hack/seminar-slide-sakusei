#!/usr/bin/env python3
"""スライドの画像（サムネイル）を取って、手本と作り直しの差を数える。読むだけ（書き込みはしない）。

使い方
  python3 sa.py thumbs <presId|tehon> <出す先> [ページ番号 ...]      1ページずつ pNNN.png（幅 1600）。番号なしで全部
  python3 sa.py diff <手本の画像フォルダ> <作り直しの画像フォルダ> <出す先> <手本の番号:作り直しの番号> ...
       差の数字（diff.json）と、左右に並べた画像（pNNN.jpg）を出す
差の物差し
  mad   … 画素の色の差の平均（0〜255・RGB の平均）。0 なら同じ
  ratio … 色の差が 32 を超えた画素の割合（%）。目で見て「違う」と分かる所の広さ
  ssim  … 形の似かた（灰色にして 400×225 で計算・1 が同じ）
"""
import os, sys, json, time, concurrent.futures as cf, urllib.request

W = 1600


def slides_ro():
    from googleapiclient.discovery import build
    from settei import creds
    c = creds(['https://www.googleapis.com/auth/drive'])
    return build('slides', 'v1', credentials=c, cache_discovery=False)


def thumbs(pid, out, pages=None):
    os.makedirs(out, exist_ok=True)
    for t in range(6):
        try:
            d = slides_ro().presentations().get(presentationId=pid, fields='slides.objectId').execute()
            break
        except Exception:
            if t == 5:
                raise
            time.sleep(10 * (t + 1))
    ids = [s['objectId'] for s in d['slides']]
    want = pages or list(range(1, len(ids) + 1))

    def one(n):
        f = os.path.join(out, f'p{n:03d}.png')
        if os.path.exists(f) and os.path.getsize(f) > 0:
            return n, 'skip'
        for t in range(6):
            try:
                r = slides_ro().presentations().pages().getThumbnail(presentationId=pid, pageObjectId=ids[n - 1],
                                                                     thumbnailProperties_thumbnailSize='LARGE',
                                                                     thumbnailProperties_mimeType='PNG').execute()
                urllib.request.urlretrieve(r['contentUrl'], f)
                return n, 'ok'
            except Exception as e:
                time.sleep(10 * (t + 1))
                err = str(e)[:120]
        return n, 'ng ' + err
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, want))
    bad = [r for r in res if r[1].startswith('ng')]
    print(len(res) - len(bad), '/', len(res), '枚', bad[:5])


def metrics(a, b):
    import numpy as np
    from PIL import Image
    A = np.asarray(Image.open(a).convert('RGB').resize((800, 450)), dtype=np.float32)
    B = np.asarray(Image.open(b).convert('RGB').resize((800, 450)), dtype=np.float32)
    d = np.abs(A - B).mean(axis=2)
    mad = float(d.mean())
    ratio = float((d > 32).mean() * 100)
    ga = np.asarray(Image.open(a).convert('L').resize((400, 225)), dtype=np.float64)
    gb = np.asarray(Image.open(b).convert('L').resize((400, 225)), dtype=np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    from numpy.lib.stride_tricks import sliding_window_view as sw
    k = 8
    wa, wb = sw(ga, (k, k))[::4, ::4], sw(gb, (k, k))[::4, ::4]
    ma, mb = wa.mean((-1, -2)), wb.mean((-1, -2))
    va, vb = wa.var((-1, -2)), wb.var((-1, -2))
    cov = ((wa - ma[..., None, None]) * (wb - mb[..., None, None])).mean((-1, -2))
    ssim = float((((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2))).mean())
    return {'mad': round(mad, 2), 'ratio': round(ratio, 2), 'ssim': round(ssim, 4)}, d


def side(a, b, out, label):
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    m, d = metrics(a, b)
    F = ImageFont.truetype(__import__('settei').FONT, 22)
    w, h = 800, 450
    heat = Image.fromarray((np.clip(d * 3, 0, 255)).astype('uint8')).convert('RGB')
    c = Image.new('RGB', (w * 3 + 40, h + 50), 'white')
    c.paste(Image.open(a).convert('RGB').resize((w, h)), (10, 40))
    c.paste(Image.open(b).convert('RGB').resize((w, h)), (w + 20, 40))
    c.paste(heat, (2 * w + 30, 40))
    dr = ImageDraw.Draw(c)
    dr.text((10, 6), f'手本 {label}', fill='#333', font=F)
    dr.text((w + 20, 6), f'作り直し（差 mad {m["mad"]}・違う所 {m["ratio"]}%・ssim {m["ssim"]}）', fill='#c00', font=F)
    dr.text((2 * w + 30, 6), '差の濃さ（白いほど違う）', fill='#333', font=F)
    c.save(out, quality=85)
    return m


def main():
    cmd = sys.argv[1]
    if cmd == 'thumbs':
        pid, out = sys.argv[2:4]
        if pid == 'tehon':
            from settei import tehon_id
            pid = tehon_id()
        pages = [int(x) for x in sys.argv[4:]] or None
        thumbs(pid, out, pages)
    elif cmd == 'diff':
        ta, tb, out = sys.argv[2:5]
        os.makedirs(out, exist_ok=True)
        f = os.path.join(out, 'diff.json')
        res = json.load(open(f)) if os.path.exists(f) else {}
        for pair in sys.argv[5:]:
            x, y = (int(v) for v in pair.split(':'))
            a, b = f'{ta}/p{x:03d}.png', f'{tb}/p{y:03d}.png'
            m = side(a, b, f'{out}/p{x:03d}.jpg', f'{x}ページ')
            res[str(x)] = m
            print(x, m)
        json.dump(res, open(f, 'w'), ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main()
