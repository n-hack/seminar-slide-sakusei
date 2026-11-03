#!/usr/bin/env python3
"""手本の Google スライドを読むだけ（presentations.get）。書き込みは一切しない。
使い方  python3 tehon_get.py <出す先のフォルダ> [presId]
  出す先/deck.json … presentations.get の結果まるごと
  出す先/pNNN.json … 1ページずつ（ページ番号は1から）"""
import json, os, sys
from googleapiclient.discovery import build
from settei import creds, TEHON   # 手本の ID は環境変数 SLIDE_TEHON_ID（読むだけ）


def slides_ro():
    c = creds(['https://www.googleapis.com/auth/drive'])
    return build('slides', 'v1', credentials=c, cache_discovery=False)


def main():
    out = sys.argv[1]
    pid = sys.argv[2] if len(sys.argv) > 2 else TEHON
    if not pid:
        raise SystemExit('手本の ID を引数か SLIDE_TEHON_ID で渡してください')
    os.makedirs(out, exist_ok=True)
    d = slides_ro().presentations().get(presentationId=pid).execute()
    json.dump(d, open(os.path.join(out, 'deck.json'), 'w'), ensure_ascii=False)
    for i, s in enumerate(d['slides'], 1):
        json.dump(s, open(os.path.join(out, f'p{i:03d}.json'), 'w'), ensure_ascii=False)
    print(d['title'], len(d['slides']), '枚', d['pageSize'])


if __name__ == '__main__':
    main()
