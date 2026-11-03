#!/usr/bin/env python3
"""設定はすべて環境変数から読む（道具の中に道・鍵・ID を書かない）。一覧は settei.example.env。

  SLIDE_SA_KEY     Google のサービスアカウントの鍵（JSON）の道。必須
  SLIDE_SUBJECT    サービスアカウントが成り代わる人のメール（ドメイン全体の委任を使うとき）。空なら委任しない
  SLIDE_SHARE_TO   作った資料に編集権限を付ける相手のメール（空なら付けない）
  SLIDE_TEHON_ID   手本の Google スライドの ID（読むだけ）
  SLIDE_WORK       作業フォルダ（手本を学んだ結果を置く所）。既定 ~/slide-work
  SLIDE_DRIVE      make.py が作る先の共有ドライブの ID（make.py を使うときだけ）
  SLIDE_FONT       日本語の字の形（ttf）。既定 assets/NotoSansJP.ttf
"""
import os

D = os.path.dirname(os.path.abspath(__file__))
SA_KEY = os.path.expanduser(os.environ.get('SLIDE_SA_KEY', ''))
SUBJECT = os.environ.get('SLIDE_SUBJECT', '')
SHARE_TO = os.environ.get('SLIDE_SHARE_TO', '')
TEHON = os.environ.get('SLIDE_TEHON_ID', '')
WORK = os.path.expanduser(os.environ.get('SLIDE_WORK', '~/slide-work'))
DRIVE = os.environ.get('SLIDE_DRIVE', '')
FONT = os.path.expanduser(os.environ.get('SLIDE_FONT', os.path.join(D, 'assets', 'NotoSansJP.ttf')))


def creds(scopes):
    from google.oauth2 import service_account
    if not SA_KEY or not os.path.exists(SA_KEY):
        raise SystemExit('SLIDE_SA_KEY にサービスアカウントの鍵（JSON）の道を入れてください')
    c = service_account.Credentials.from_service_account_file(SA_KEY, scopes=scopes)
    return c.with_subject(SUBJECT) if SUBJECT else c


def tehon_id():
    if not TEHON:
        raise SystemExit('SLIDE_TEHON_ID に手本の Google スライドの ID を入れてください')
    return TEHON
