#!/usr/bin/env python3
"""台本や情報のテキスト（Markdown）を渡すと、手本（Google スライド・読むだけ）の型を選んで Google スライドを作る。

使い方
  python3 make.py 台本.md                      新しく作る（共有ドライブ SLIDE_DRIVE /「試し（スライド）」）
  python3 make.py 台本.md --pres <presId>      その資料の中身を全部消して作り直す（URL は変わらない）
  python3 make.py 台本.md --plan               作らずに、型の選び方と枚数だけ出す（plan.json）
  python3 make.py 台本.md --kata               ★手本の1ページの層をそのまま写して中身だけ差し替える（完コピ・いつもこれ）
                                              型の記録は assets/kata.json（作り直し：python3 kata.py build <deck.json> <img/>）
                                              設定の kata_kara: / kata_made: で手本のどのあたり（0〜1）の型を使うか決める
  python3 make.py 台本.md --folder 名前         置き場のフォルダ名を変える
  続けて検査：python3 kensa.py <presId> <書き出し先>   （はみ出し・重なり・読めない字・禁止キャラ／20枚ずつの一覧）

台本の書き方（1枚＝空行で区切った1かたまり。何も書かなければ普通の「1メッセージ」）
  ---                         先頭の --- ～ --- は設定（title: 資料名）
  # 題 / 副題                 表紙（黒と金の写真・極太の題）。「実績: A | B | C」の行で下に丸アイコン3つ
  ## 章の名前                 章の扉（紺の全面＋金の細線）。この後の上の帯の見出しにもなる
  @帯 見出し                  この後の上の帯の見出し（@帯 なし で消す）
  **語**                      言いたい語だけ赤（書かなければ「」の中・数字＋単位を自動で赤）
  ==語==                      金ベージュの帯に赤文字（マーカー）
  [待機] 1行目 / 2行目         待機画面
  [問い] 【質問1】 / 本文       上の帯「皆さんに質問です」＋考える人
  [悩み] 見出し / 「声」 / 「声」  白い吹き出しを互い違いに並べる（右に困った人）
  [比較] 見出し / 左の名前: 説明 / 右の名前: 説明 / 下の一言   ＝ vs の四角2つ（[等式] は間が ＝）
  [番号] 見出し / 項目 / 項目     紺の四角に白い数字（[番号*] は1項目ずつ濃くして項目の数だけめくる）
  [流れ] 見出し / A → B → C     白い五角形の矢印を横に（[流れ*] は1つずつ足してめくる）
  [矢印] 前の文 / 答え           下向きの矢印で「だから→答え」
  [カード] 見出し / 名前: 説明 / … 紺の見出しつきの白いカード（2〜6枚）
  [数字] 前の言葉 / 345 / 件 / 後の言葉   数字を大きく
  [写真] 本文                   金のぼけ写真の背景（特典・限定・感謝・締め）
  [暗い] 本文                   濃い灰色の写真＋白い帯（「理由」などの見出し）
  [人:気持ち] を先頭の行に足すと人物を右に置く（気持ち＝考える 悩む 説明 成功 PC 挨拶 調べる AI 贈り物）
  [人なし] で人物を置かない
  [型:227] を先頭の行に足すと、手本のそのページの型で作る（字の箱の数が合うときだけ）
"""
import argparse, json, os, re, sys, time, hashlib, itertools
from PIL import ImageFont

D = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(D, 'assets')
from settei import DRIVE                 # 作る先の共有ドライブ（環境変数 SLIDE_DRIVE）
FOLDER_NAME = '試し（スライド）'
NAVY, RED, GOLDBOX, WHITE, GOLD, GRAY, LINE = '#29274D', '#A71E26', '#E8D8A1', '#FFFFFF', '#E3C27A', '#868898', '#C9CCD6'
FONT = 'Noto Sans JP'
W, H = 720.0, 405.0
BAND = 19.4

# 人物（ソコスト・線と差し色を紺に）。気持ち → 絵
HITO = {
    '考える': ['27534', '27151', '27188', '27539', '27122', '27142'],
    '悩む': ['29394', '29402', '29412', '29418', '19410', '19421', '16939', '16953', '27232', '27251'],
    '説明': ['7849', '7852', '7861', '7863', '7888', '7891', '17459', '17467', '17484', '17500'],
    '成功': ['13536', '13550', '11363', '11369', '16911', '16918', '13404', '13421', '12359', '12368', '21654', '21637', '7911', '7913'],
    'PC': ['26698', '26707', '26712', '26719', '9759'],
    '挨拶': ['27646', '27653'],
    '調べる': ['27614', '27624'],
    'AI': ['11779'],
    '贈り物': ['29340'],
    'グラフ': ['17814', '9780'],
}
# 言葉 → アイコン（Material Symbols・紺1色）
ICON_WORDS = [
    (('AI', 'エージェント', 'ロボ'), 'smart_toy'), (('お金', '売上', '収入', '収益', '円', '利益'), 'payments'),
    (('時間', '時短', '分', '24時間'), 'schedule'), (('人', '社員', '外注', 'チーム', '組織'), 'groups'),
    (('家', '自宅'), 'home'), (('予約', '日程', 'カレンダー', '毎日', '毎週'), 'calendar_month'),
    (('アイデア', 'ひらめ', '気づ'), 'lightbulb'), (('調べ', 'リサーチ', '調査', '検索', '競合'), 'search'),
    (('書く', '文章', '投稿', '下書き', '記事', 'note'), 'edit_note'), (('集客', '発信', 'SNS', '告知'), 'campaign'),
    (('チャット', '質問', '相談', '会話'), 'chat'), (('メール', '連絡', '送る'), 'mail'), (('伸び', '成長', 'アップ', 'UP'), 'trending_up'),
    (('経費', '節約', '削減'), 'savings'), (('自動', '速', '一瞬'), 'bolt'), (('完了', 'できる', 'OK'), 'check_circle'),
    (('注意', '危険', '罠'), 'warning'), (('権限', '鍵', '守'), 'lock'), (('学', '教育', '勉強', '講座'), 'school'),
    (('仕事', '業務', '会社'), 'work'), (('資料', '仕様書', 'シート', '表'), 'description'), (('数字', '分析', 'データ'), 'bar_chart'),
    (('設定', '仕組み', '設計'), 'settings'), (('起動', '始め', 'スタート'), 'rocket_launch'), (('寝', '夜'), 'bedtime'),
    (('顧客', 'お客様', '対応', 'サポート', 'CS'), 'support_agent'), (('販売', '売る', '購入'), 'shopping_cart'),
    (('商品', '価格', '単価'), 'sell'), (('特典', 'プレゼント'), 'redeem'), (('実績', '結果', '成果'), 'workspace_premium'),
    (('記録', '保存', 'データベース'), 'database'), (('フォルダ', 'ファイル'), 'folder'), (('改善', '更新', '繰り返'), 'autorenew'),
    (('考え', '判断', '決める'), 'psychology'), (('LINE', '登録'), 'forum'), (('市場', 'ターゲット', '狙'), 'target'),
    (('つなぐ', '連携', '共有'), 'hub'), (('世界', '海外'), 'language'), (('店', 'ショップ'), 'storefront'),
    (('信頼', '握手', '契約'), 'handshake'), (('目標', 'KPI', 'KGI', 'ゴール'), 'flag'), (('待', '止ま'), 'hourglass_top'),
]
HITO_WORDS = [(('？', '?', '思いますか', 'ますか'), '考える'), (('悩', '困', '疲', '止ま', '減って', '足りない', '忙し', '壁'), '悩む'),
              (('稼', '伸び', '増え', '成功', '自由', '変わ', '叶'), '成功'), (('AIエージェント', '任せ', '丸投げ'), 'PC'),
              (('調べ', 'リサーチ', '分析'), '調べる'), (('ありがとう', 'よろしく', '感謝'), '挨拶'), (('特典', 'プレゼント'), '贈り物')]

_FONTS = {}


def font(wt):
    if wt not in _FONTS:
        f = ImageFont.truetype(__import__('settei').FONT, 100)
        try:
            f.set_variation_by_axes([wt])
        except Exception:
            pass
        _FONTS[wt] = f
    return _FONTS[wt]


def text_w(s, size, wt=700):
    """その大きさ（pt）で1行の幅（pt）"""
    return font(wt).getlength(s) * size / 100.0


LH = 1.45   # Noto Sans JP の1行の高さ（字の大きさの倍・行間100%のとき）
PAD = 7.2   # 文字の箱の内側の余白（Google スライドの既定）


# ---------- 台本を読む ----------
def runs_of(line, auto=True):
    """1行を [(文字, 色の役)] に。**赤** ==マーカー== 。書いていなければ「」と数字＋単位を自動で赤"""
    if '**' not in line and '==' not in line and auto:
        m = re.search(r'「[^」]{1,24}」', line) or re.search(r'[0-9０-９][0-9０-９,.,〜~→]*(万円|億円|万|億|円|件|本|人|名|社|個|つ|倍|%|％|時間|分|日|ヶ月|か月|年|体|段|STEP)', line)
        if m and len(m.group(0)) < len(line):
            return [(line[:m.start()], 'n'), (line[m.start():m.end()], 'r'), (line[m.end():], 'n')]
        return [(line, 'n')]
    out, i = [], 0
    for m in re.finditer(r'\*\*(.+?)\*\*|==(.+?)==', line):
        out.append((line[i:m.start()], 'n'))
        out.append((m.group(1), 'r') if m.group(1) is not None else (m.group(2), 'm'))
        i = m.end()
    out.append((line[i:], 'n'))
    return [r for r in out if r[0]]


def plain(line):
    return re.sub(r'\*\*|==', '', line)


def parse(md):
    meta, body = {}, md
    m = re.match(r'---\n(.*?)\n---\n', md, re.S)
    if m:
        for l in m.group(1).splitlines():
            if ':' in l:
                k, v = l.split(':', 1)
                meta[k.strip()] = v.strip()
        body = md[m.end():]
    blocks = [b.strip('\n') for b in re.split(r'\n\s*\n', body) if b.strip()]
    slides, label, sec_no = [], None, 0
    for b in blocks:
        lines = [l.rstrip() for l in b.splitlines() if l.strip() and not l.strip().startswith('//')]
        if not lines:
            continue
        hito = None
        if lines[0].startswith('@帯'):
            v = lines[0][2:].strip()
            label = None if v in ('', 'なし') else v
            lines = lines[1:]
            if not lines:
                continue
        kata_page = None
        mt = re.match(r'\[型:(\d+)\]\s*', lines[0])
        if mt:   # 手本のこのページの型で作る（例 [型:227]）
            kata_page = int(mt.group(1))
            lines[0] = lines[0][mt.end():]
            lines = [l for l in lines if l.strip()]
        mh = re.match(r'\[人(?::(.+?))?\]\s*', lines[0])
        if mh:
            hito = mh.group(1) or 'auto'
            lines[0] = lines[0][mh.end():]
            lines = [l for l in lines if l.strip()]
        if lines and lines[0].startswith('[人なし]'):
            hito = 'なし'
            lines[0] = lines[0][5:].strip()
            lines = [l for l in lines if l]
        head = lines[0]
        if head.startswith('# '):
            parts = [p.strip() for p in head[2:].split('/')]
            jisseki = []
            for l in lines[1:]:
                if l.startswith('実績:'):
                    jisseki = [p.strip() for p in l[3:].split('|')]
            slides.append({'kind': 'hyoushi', 'title': parts[0], 'sub': parts[1] if len(parts) > 1 else '', 'top': meta.get('kicker', ''),
                           'jisseki': jisseki})
            continue
        if head.startswith('## '):
            sec_no += 1
            t = head[3:].strip()
            label = re.sub(r'^[0-9０-９]+[.．、\s]*', '', t)
            slides.append({'kind': 'tobira', 'title': t, 'no': sec_no, 'sub': lines[1] if len(lines) > 1 else ''})
            continue
        mk = re.match(r'\[(\S+?)(\*?)\]\s*(.*)', head)
        kind, star, rest = (mk.group(1), mk.group(2), mk.group(3)) if mk else (None, '', head)
        items = ([rest] if rest else []) + lines[1:] if mk else lines
        items = [x.strip() for x in itertools.chain.from_iterable(i.split(' / ') for i in items) if x.strip()]
        base = {'label': label, 'hito': hito, 'kata_page': kata_page}
        if kind is None:
            k = 'message'
            if any('→' in x for x in items) and len(items) <= 2 and len(items[-1].split('→')) >= 3:
                k = 'nagare'
            slides.append({**base, 'kind': k, 'items': items})
        elif kind == '番号' and star:
            n = len(items) - 1
            for f in range(n):
                slides.append({**base, 'kind': '番号', 'items': items, 'focus': f, 'build_key': f'b{len(slides)}_{n}' if f == 0 else None})
            for x in slides[-n:]:
                x['build_key'] = slides[-n]['build_key']
        elif kind == '流れ' and star:
            steps = [s.strip() for s in items[-1].split('→')]
            bk = f'f{len(slides)}'
            for f in range(1, len(steps) + 1):
                slides.append({**base, 'kind': '流れ', 'items': items, 'upto': f, 'build_key': bk})
        else:
            slides.append({**base, 'kind': kind, 'items': items})
    return meta, slides


# ---------- 文字の大きさを箱に合わせる ----------
def fit(lines, w, h, smax, smin=12, wt=700, spacing=1.0):
    """複数行（runs）が箱 w×h に収まる最大の大きさ。
    横：箱の内側の余白（左右 PAD）を引いた幅に収める（超えると Google スライドが勝手に折り返す）
    縦：字の高さの合計が箱の高さに収まる（上下の余白は、真ん中ぞろえなら外にはみ出しても見た目は崩れない）
    小さくしても横に入らない時だけ、いちばん長い行を句読点・助詞のあとで2つに折る"""
    lines = [l for l in lines]
    for _ in range(4):
        s = smax
        while s >= smin:
            mw = max(text_w(''.join(r[0] for r in l), s, wt) for l in lines)
            th = len(lines) * s * LH * spacing
            if mw <= (w - 2 * PAD) * 0.97 and th <= h * 0.98:
                return s, lines
            s -= 1
        mw = max(text_w(''.join(r[0] for r in l), smin, wt) for l in lines)
        if mw <= (w - 2 * PAD) * 0.97:
            return smin, lines        # 横は入る＝縦だけ足りない。折ると悪くなるので折らない
        idx = max(range(len(lines)), key=lambda i: text_w(''.join(r[0] for r in lines[i]), 10, wt))
        if len(''.join(r[0] for r in lines[idx])) < 4:
            break
        lines = lines[:idx] + split_runs(lines[idx]) + lines[idx + 1:]
    return smin, lines


def split_runs(l):
    s = ''.join(r[0] for r in l)
    n = len(s)
    best, bi = 1e9, n // 2
    for i in range(1, n):
        if s[i - 1] in '、。，,）」』！？' or s[i - 1] in 'はがをにでともへの' and s[i] not in 'はがをにでともへの、。':
            d = abs(i - n / 2)
            if d < best:
                best, bi = d, i
    a, b, pos = [], [], 0
    for t, c in l:
        if pos + len(t) <= bi:
            a.append((t, c))
        elif pos >= bi:
            b.append((t, c))
        else:
            a.append((t[:bi - pos], c)); b.append((t[bi - pos:], c))
        pos += len(t)
    return [a, b]


def hex2rgb(h):
    h = h.lstrip('#')
    return {'red': int(h[0:2], 16) / 255, 'green': int(h[2:4], 16) / 255, 'blue': int(h[4:6], 16) / 255}


def pt(v):
    return {'magnitude': v, 'unit': 'PT'}


# ---------- Google スライドへの書き込み ----------
class Deck:
    def __init__(self, sl, pid, urls, ratio):
        self.sl, self.pid, self.reqs, self.n = sl, pid, [], 0
        self.U, self.ar = urls, ratio
        self.tag = time.strftime('%H%M%S')
        self.sid = None
        self.hito_i = {}
        self.kata_build = {}
        self.layout = []     # 検査用：置いた物の記録
        self.page = 0

    def nid(self, p):
        self.n += 1
        return f'{p}{self.tag}_{self.n:05d}'

    def slide(self, bg):
        self.page += 1
        sid = self.nid('s')
        self.reqs.append({'createSlide': {'objectId': sid, 'slideLayoutReference': {'predefinedLayout': 'BLANK'}}})
        self.reqs.append({'updatePageProperties': {'objectId': sid, 'fields': 'pageBackgroundFill',
                          'pageProperties': {'pageBackgroundFill': {'stretchedPictureFill': {'contentUrl': self.U[bg]}}}}})
        self.sid = sid
        self.layout.append({'page': self.page, 'bg': bg, 'objs': []})
        return sid

    def _rec(self, role, oid, x, y, w, h, **kw):
        self.layout[-1]['objs'].append({'role': role, 'id': oid, 'box': [round(x, 1), round(y, 1), round(w, 1), round(h, 1)], **kw})

    def rect(self, x, y, w, h, fill, line=None, lw=1.5, shape='RECTANGLE', shadow=False, rot=0, role='形'):
        oid = self.nid('b')
        if shape == 'FLOWCHART_MERGE':   # 下向きの三角（API では作れない）＝ 三角を上下に返す
            shape = 'TRIANGLE'
            tf = {'scaleX': 1, 'scaleY': -1, 'translateX': x, 'translateY': y + h, 'unit': 'PT'}
            size = {'width': pt(w), 'height': pt(h)}
        elif rot == 90:   # 90度回す（下向きの山形）：見た目の箱 (x, y, w, h) に収まるよう、元の形は h×w で作る
            tf = {'scaleX': 0, 'scaleY': 0, 'shearX': -1, 'shearY': 1, 'translateX': x + w, 'translateY': y, 'unit': 'PT'}
            size = {'width': pt(h), 'height': pt(w)}
        else:
            tf = {'scaleX': 1, 'scaleY': 1, 'translateX': x, 'translateY': y, 'unit': 'PT'}
            size = {'width': pt(w), 'height': pt(h)}
        self.reqs.append({'createShape': {'objectId': oid, 'shapeType': shape, 'elementProperties': {
            'pageObjectId': self.sid, 'size': size, 'transform': tf}}})
        props = {'shapeBackgroundFill': {'solidFill': {'color': {'rgbColor': hex2rgb(fill)}}} if fill else {'propertyState': 'NOT_RENDERED'}}
        props['outline'] = {'outlineFill': {'solidFill': {'color': {'rgbColor': hex2rgb(line)}}}, 'weight': pt(lw)} if line else {'propertyState': 'NOT_RENDERED'}
        if shadow:
            props['shadow'] = {'type': 'OUTER', 'alignment': 'TOP_LEFT', 'blurRadius': pt(6), 'color': {'rgbColor': hex2rgb('#000000')},
                               'alpha': 0.18, 'rotateWithShape': False,
                               'transform': {'scaleX': 1, 'scaleY': 1, 'translateX': 3, 'translateY': 3, 'unit': 'PT'}}
        self.reqs.append({'updateShapeProperties': {'objectId': oid, 'fields': ','.join(props.keys()), 'shapeProperties': props}})
        self._rec(role, oid, x, y, w, h, fill=fill)
        return oid

    def text(self, x, y, w, h, lines, size, color=NAVY, wt=700, align='CENTER', valign='MIDDLE', spacing=100, role='文字', red=RED):
        """lines: [[(文字, 役)]]  役 n=基本色 r=赤 m=マーカー（金の帯に赤） w=白 g=金 l=薄い灰"""
        oid = self.nid('t')
        self.reqs.append({'createShape': {'objectId': oid, 'shapeType': 'TEXT_BOX', 'elementProperties': {
            'pageObjectId': self.sid, 'size': {'width': pt(w), 'height': pt(h)},
            'transform': {'scaleX': 1, 'scaleY': 1, 'translateX': x, 'translateY': y, 'unit': 'PT'}}}})
        full = '\n'.join(''.join(r[0] for r in l) for l in lines)
        self.reqs.append({'insertText': {'objectId': oid, 'text': full}})
        i = 0
        cmap = {'n': color, 'r': red, 'm': RED, 'w': WHITE, 'g': GOLD, 'l': GRAY, 'k': NAVY}
        for li, l in enumerate(lines):
            for s, c in l:
                if s:
                    st = {'fontSize': pt(size), 'foregroundColor': {'opaqueColor': {'rgbColor': hex2rgb(cmap.get(c, color))}},
                          'weightedFontFamily': {'fontFamily': FONT, 'weight': wt}, 'bold': wt >= 700}
                    f = 'fontSize,foregroundColor,weightedFontFamily,bold'
                    if c == 'm':
                        st['backgroundColor'] = {'opaqueColor': {'rgbColor': hex2rgb(GOLDBOX)}}
                        f += ',backgroundColor'
                    self.reqs.append({'updateTextStyle': {'objectId': oid, 'textRange': {'type': 'FIXED_RANGE', 'startIndex': i, 'endIndex': i + len(s)},
                                      'fields': f, 'style': st}})
                i += len(s)
            i += 1
        self.reqs.append({'updateParagraphStyle': {'objectId': oid, 'textRange': {'type': 'ALL'}, 'fields': 'alignment,lineSpacing,spaceAbove,spaceBelow',
                          'style': {'alignment': align, 'lineSpacing': spacing, 'spaceAbove': pt(0), 'spaceBelow': pt(0)}}})
        self.reqs.append({'updateShapeProperties': {'objectId': oid, 'fields': 'contentAlignment,autofit.autofitType',
                          'shapeProperties': {'contentAlignment': valign, 'autofit': {'autofitType': 'NONE'}}}})
        cols = sorted({cmap.get(c, color) for l in lines for s, c in l if s.strip()})
        self._rec(role, oid, x, y, w, h, text=full, size=size, wt=wt, spacing=spacing, colors=cols, align=align,
                  lines=[''.join(r[0] for r in l) for l in lines], marker=any(c == 'm' for l in lines for s, c in l))
        return oid

    def fit_text(self, x, y, w, h, lines, smax, smin=12, wt=700, spacing=100, fit_spacing=None, **kw):
        s, ls = fit(lines, w, h, smax, smin, wt, (fit_spacing or spacing) / 100.0)
        return self.text(x, y, w, h, ls, s, wt=wt, spacing=spacing, **kw), s, ls

    def image(self, key, x, y, w, h, role='絵'):
        if key not in self.U and key.startswith('deco/g_') and not hasattr(self.U, '__missing__'):   # 空回し（Fake）では通常どおり記録する
            # 空回しで作らなかったグラデ：上げ直さず、左の色の板で置く（止めない）
            return self.rect(x, y, w, h, '#' + key.split('_')[1], role=role)
        oid = self.nid('i')
        self.reqs.append({'createImage': {'objectId': oid, 'url': self.U[key], 'elementProperties': {
            'pageObjectId': self.sid, 'size': {'width': pt(w), 'height': pt(h)},
            'transform': {'scaleX': 1, 'scaleY': 1, 'translateX': x, 'translateY': y, 'unit': 'PT'}}}})
        self._rec(role, oid, x, y, w, h, key=key)
        return oid

    def put(self, key, cx, y, h, maxw=None, role='人物'):
        """縦の高さ h で真ん中 cx に置く（幅が maxw を超えるなら縮める）"""
        r = self.ar[key]
        w = h * r
        if maxw and w > maxw:
            w, h = maxw, maxw / r
        return self.image(key, cx - w / 2, y, w, h, role=role)

    def icon(self, name, x, y, s):
        return self.image(f'icon/{name}.png', x, y, s, s, role='アイコン')

    def bands(self, label=None):
        top = 34 if label else BAND
        self.rect(0, 0, W, top, NAVY, role='帯')
        if label:
            s, ls = fit([[(label, 'w')]], W - 40, top, 16, 10)
            self.text(20, 0, W - 40, top, ls, s, color=WHITE, role='帯の見出し')
        self.rect(0, H - BAND, W, BAND, NAVY, role='帯')
        return top

    def pick_hito(self, mood):
        lst = HITO.get(mood) or HITO['説明']
        i = self.hito_i.get(mood, 0)
        self.hito_i[mood] = i + 1
        return f'soco/{lst[i % len(lst)]}.png'

    def flush(self, every=450):
        for k in range(0, len(self.reqs), every):
            for t in range(5):
                try:
                    self.sl.presentations().batchUpdate(presentationId=self.pid, body={'requests': self.reqs[k:k + every]}).execute()
                    break
                except Exception as e:
                    if t == 4 or ('429' not in str(e) and '500' not in str(e) and '503' not in str(e) and 'retrieving the image' not in str(e)):
                        raise
                    time.sleep(20 * (t + 1))
        self.reqs = []


def icon_for(text, used=()):
    for words, name in ICON_WORDS:
        if any(w in text for w in words) and name not in used:
            return name
    for fallback in ('task_alt', 'star', 'flag', 'bolt', 'lightbulb', 'check_circle'):
        if fallback not in used:
            return fallback
    return 'task_alt'


def mood_for(text):
    for words, m in HITO_WORDS:
        if any(w in text for w in words):
            return m
    return '説明'


# ---------- 型ごとの作り ----------
MSG_VARS = ['plain', 'card', 'banner', 'beige', 'plain', 'sankaku', 'card', 'banner']


def r_message(d, s):
    """1メッセージ。手本の飾りを順に使う：そのまま／白い角丸の箱＋影＋人物がのぞく／紺のグラデの帯に白と金の字／
    金ベージュの横帯／▶の印。どれにするかは台本の文字から決める（同じ台本なら毎回同じ）"""
    items = s['items']
    top = d.bands(s.get('label'))
    hito = s.get('hito')
    n_chars = sum(len(plain(x)) for x in items)
    var = s.get('var') or MSG_VARS[(d.page + n_chars) % len(MSG_VARS)]
    if len(items) > 3 or n_chars > 60:
        var = 'plain'
    lines = [runs_of(x) for x in items]
    sub = None
    if len(items) >= 2 and len(plain(items[-1])) > 0 and items[-1].startswith('（'):
        sub = lines.pop()
    if var == 'card':
        mood = mood_for(''.join(items)) if hito in (None, 'auto', 'なし') else hito
        d.rect(60, top + 48, 470, H - top - BAND - 100, WHITE, line=NAVY, lw=1.2, shape='ROUND_RECTANGLE', shadow=True, role='箱')
        if mood == '成功':
            d.image('deco/hosha.png', 520, top + 30, 200, 200, role='飾り')
        if hito != 'なし':
            d.put(d.pick_hito(mood), 620, top + 50, H - top - BAND - 70, maxw=190)
        d.fit_text(78, top + 58, 434, H - top - BAND - 120, lines, 30, 14, spacing=130, role='箱の文字')
        return
    if var in ('banner', 'beige') and len(lines) >= 1:
        last = lines[-1]
        pre = lines[:-1]
        y0 = top + 30
        if pre:
            _, s1, ls = d.fit_text(60, y0, W - 120, 110, pre, 26, 14, spacing=130)
            y0 += 120
        else:
            y0 += 70
        if var == 'banner':
            d.image('deco/grad.png', 50, y0, W - 100, 86, role='バナー')
            d.layout[-1]['objs'][-1]['fill'] = '#4B4A72'
            runs = [(t, 'g' if c in ('r', 'm') else 'w') for t, c in last]
            d.fit_text(66, y0, W - 132, 86, [runs], 32, 14, color=WHITE, role='箱の文字')
        else:
            d.rect(0, y0, W, 80, GOLDBOX, role='マーカー')
            d.fit_text(40, y0, W - 80, 80, [last], 32, 14, role='箱の文字')
        if hito not in (None, 'なし'):
            d.put(d.pick_hito(hito if hito != 'auto' else mood_for(''.join(items))), 640, H - BAND - 150, 140, maxw=110)
        return
    if var == 'sankaku' and lines:
        lines[-1] = [('▶ ', 'k')] + lines[-1]
    if hito is None:
        # 文字が短い・3行以内なら、3枚に1枚くらい人物を右に置く（手本の「文字が左・人物が右」）
        hito = 'auto' if (d.page % 3 == 0 and len(items) <= 3 and n_chars <= 40) else 'なし'
    if hito != 'なし':
        mood = mood_for(''.join(items)) if hito == 'auto' else hito
        if mood == '成功':
            d.image('deco/hosha.png', 490, top + 30, 200, 200, role='飾り')
        d.put(d.pick_hito(mood), 590, top + 40, H - top - BAND - 60, maxw=210)
        x0, w0 = 24, 456
    else:
        x0, w0 = 40, W - 80
    area_h = H - top - BAND - (60 if sub else 30)
    smax = 34 if n_chars <= 30 else 28
    d.fit_text(x0, top + 15, w0, area_h, lines, smax, 16, spacing=130)
    if sub:
        d.fit_text(x0, H - BAND - 56, w0, 40, [sub], 16, 11, wt=700)


def r_taiki(d, s):
    d.slide('bg_navy.png')
    d.rect(80, 60, W - 160, H - 120, '#D5D4DE', shape='ROUND_RECTANGLE', role='形')
    it = s['items'] or ['まもなくセミナーが始まります']
    d.fit_text(110, 130, W - 220, 50, [runs_of(it[0], False)], 30, 14, color='#303558')
    if len(it) > 1:
        d.fit_text(110, 205, W - 220, 70, [runs_of(x, False) for x in it[1:]], 18, 11, color='#303558', spacing=150)


def r_hyoushi(d, s):
    d.slide('bg_cover.jpg')
    if s.get('top'):
        d.fit_text(60, 34, W - 120, 30, [[(s['top'], 'g')]], 16, 11, color=GOLD)
    t = s['title']
    parts = [p for p in re.split(r'[｜|]', t) if p]
    lines = [[(parts[0], 'w')]] + ([[(p, 'g')] for p in parts[1:]] if len(parts) > 1 else [])
    d.fit_text(40, 68, W - 80, 170, lines, 64, 28, wt=900, color=WHITE, spacing=100)
    d.rect(230, 250, 260, 1.5, GOLD, role='線')
    if s.get('sub'):
        d.rect(200, 266, 320, 40, NAVY, line=GOLD, lw=1.5, shape='ROUND_RECTANGLE', role='形')
        d.fit_text(200, 266, 320, 40, [[(s['sub'], 'w')]], 17, 11, color=WHITE)
    js = s.get('jisseki') or []
    for k, j in enumerate(js[:3]):
        cx = W / 2 + (k - (len(js[:3]) - 1) / 2) * 210
        d.rect(cx - 98, 322, 28, 28, GOLD, shape='ELLIPSE', role='形')
        d.icon(icon_for(j), cx - 94, 326, 20)
        d.fit_text(cx - 66, 318, 170, 36, [runs_of(j, False)], 15, 9, color=WHITE, align='START', red=GOLD)


def r_tobira(d, s):
    d.slide('bg_navy.png')
    d.rect(0, 40, W, 1.5, GOLD, role='線')
    d.rect(0, H - 41.5, W, 1.5, GOLD, role='線')
    d.fit_text(60, 110, W - 120, 46, [[(f'【ノウハウ{s["no"]}】', 'w')]], 22, 12, color=WHITE)
    d.fit_text(60, 160, W - 120, 90, [[(s['title'], 'g')]], 40, 18, color=GOLD, wt=900)
    if s.get('sub'):
        d.fit_text(60, 258, W - 120, 40, [runs_of(s['sub'], False)], 17, 10, color=WHITE)


def r_toi(d, s):
    top = d.bands('皆さんに質問です')
    it = s['items']
    q = it[0] if it[0].startswith('【') else None
    body = it[1:] if q else it
    d.put(d.pick_hito('考える'), 120, top + 40, 170, maxw=170)
    if q:
        d.fit_text(225, top + 34, 440, 30, [[(q, 'r')]], 18, 11, align='START')
    d.fit_text(225, top + 66, 460, 150, [runs_of(x) for x in body], 26, 13, align='START', valign='TOP', spacing=130)
    d.rect(225, top + 230, 450, 1, LINE, role='線')
    d.fit_text(225, top + 240, 450, 46, [[('当てはまる方は ', 'n'), ('リアクション', 'r'), (' でお知らせください', 'n')]], 15, 10, align='START')


def r_nayami(d, s):
    top = d.bands(s.get('label') or 'よくあるお悩み')
    it = s['items']
    head = it[0] if not it[0].startswith('「') else 'こんな**お悩み**、ありませんか？'
    voices = [x for x in (it[1:] if head == it[0] else it)][:4]
    d.fit_text(30, top + 6, 460, 46, [runs_of(head)], 26, 14)
    n = len(voices)
    gap = (H - top - BAND - 70) / max(n, 1)
    bh = min(56, gap - 10)
    for k, v in enumerate(voices):
        x = 30 if k % 2 == 0 else 80
        y = top + 60 + k * gap
        d.rect(x, y, 410, bh, WHITE, line=NAVY, lw=1.5, shape='ROUND_RECTANGLE', shadow=True, role='箱')
        d.rect(x + 14, y + bh / 2 - 15, 16, 16, NAVY, shape='ELLIPSE', role='形')
        d.rect(x + 9, y + bh / 2 + 3, 26, 12, NAVY, shape='ROUND_RECTANGLE', role='形')
        d.fit_text(x + 44, y, 360, bh, [runs_of(v.strip('「」'), False)], 17, 10, align='START', role='箱の文字')
    if s.get('hito') != 'なし':
        d.put(d.pick_hito('悩む'), 600, top + 70, 210, maxw=200)


def split_kv(x):
    for sep in (':', '：'):
        if sep in x:
            a, b = x.split(sep, 1)
            return a.strip(), b.strip()
    return x.strip(), ''


def r_hikaku(d, s, eq=False):
    top = d.bands(s.get('label'))
    it = s['items']
    head = it[0]
    L, R = split_kv(it[1]) if len(it) > 1 else ('', ''), split_kv(it[2]) if len(it) > 2 else ('', '')
    foot = it[3] if len(it) > 3 else None
    d.fit_text(40, top + 6, W - 80, 44, [runs_of(head)], 24, 13)
    bw, bh, by = 250, 190 if foot else 220, top + 56
    used = []
    for bx, (name, desc), col in [(70, L, 'n'), (400, R, 'r')]:
        d.rect(bx, by, bw, bh, WHITE, line=NAVY, lw=1.5, shadow=True, role='箱')
        ic = icon_for(desc + name, used); used.append(ic)
        d.rect(bx + bw / 2 - 40, by + 16, 80, 80, '#EEF0F5', role='形')
        d.icon(ic, bx + bw / 2 - 30, by + 26, 60)
        d.rect(bx + 30, by + 104, bw - 60, 28, NAVY if col == 'n' else RED, shape='ROUND_RECTANGLE', role='形')
        d.fit_text(bx + 30, by + 104, bw - 60, 28, [[(name, 'w')]], 15, 9, color=WHITE, role='箱の文字')
        if desc:
            d.fit_text(bx + 8, by + 134, bw - 16, bh - 142, [[(desc, col)]], 19, 10, role='箱の文字')
    d.fit_text(320, by + bh / 2 - 26, 80, 52, [[('＝' if eq else 'vs', 'n')]], 30, 14, wt=900)
    if foot:
        d.fit_text(150, by + bh + 12, 420, 44, [runs_of(foot)], 24, 12, role='文字')


def r_bangou(d, s):
    top = d.bands(s.get('label'))
    it = s['items']
    head, rows = it[0], it[1:][:6]
    f = s.get('focus')
    hito = s.get('hito') != 'なし'
    d.fit_text(30, top + 6, 500 if hito else W - 60, 46, [runs_of(head)], 26, 13, align='CENTER')
    n = len(rows)
    gap = min(70, (H - top - BAND - 70) / max(n, 1))
    tw = 400 if hito else 560
    sq = min(34, gap - 14)
    # 行の字の大きさはそろえる（いちばん長い行に合わせる）
    rsz = min(fit([[(plain(r), 'n')]], tw - sq - 6, sq + 12, 22, 10)[0] for r in rows) if rows else 22
    used = []
    for k, r in enumerate(rows):
        y = top + 64 + k * gap
        on = f is None or k == f
        ic = icon_for(r, used); used.append(ic)
        if on:
            d.icon(ic, 50 + tw + 48 - sq, y, sq)
        d.rect(50, y, sq, sq, NAVY if on else GRAY, role='形')
        d.fit_text(50, y, sq, sq, [[(str(k + 1), 'w')]], 18, 9, color=WHITE, wt=900)
        col = None if on else 'l'
        runs = runs_of(r) if on else [(plain(r), 'l')]
        d.fit_text(98, y - 6, tw - sq - 6, sq + 12, [runs], rsz, 10, align='START', color=NAVY if on else GRAY)
        d.rect(50, y + sq + 6, tw + 48, 1, LINE, role='線')
    if hito:
        # 1項目ずつめくる時は、めくっている間ずっと同じ人物にする
        if not f or not getattr(d, 'build_hito', None):
            mood = s['hito'] if s.get('hito') not in (None, 'auto') else '説明'
            d.build_hito = d.pick_hito(mood)
        d.put(d.build_hito, 615, top + 70, 210, maxw=180)


def r_nagare(d, s):
    top = d.bands(s.get('label'))
    it = s['items']
    head = it[0] if len(it) > 1 else ''
    steps = [x.strip() for x in it[-1].split('→')][:6]
    upto = s.get('upto', len(steps))
    if head:
        d.fit_text(30, top + 10, W - 60, 50, [runs_of(head)], 26, 13)
    n = len(steps)
    cw = (W - 60) / n
    used = []
    for k, st in enumerate(steps):
        x = 30 + k * cw
        vis = k < upto
        d.rect(x, 170, cw - 6, 76, WHITE if vis else '#ECEDF1', line=NAVY if vis else LINE, lw=1.5,
               shape='HOME_PLATE' if k < n - 1 else 'RECTANGLE', shadow=vis, role='箱')
        ic = icon_for(st, used); used.append(ic)
        if vis:
            cx = x + (cw - 6) / 2 - (6 if k < n - 1 else 0)
            d.rect(cx - 12, 140, 24, 24, NAVY, shape='ELLIPSE', role='形')
            d.fit_text(cx - 12, 140, 24, 24, [[(str(k + 1), 'w')]], 13, 8, color=WHITE, wt=900)
            d.icon(ic, cx - 22, 186, 44)
            d.fit_text(x, 256, cw - 6, 60, [runs_of(st, False)], 17, 9, role='文字')


def r_yajirushi(d, s):
    top = d.bands(s.get('label'))
    it = s['items']
    pre, ans = it[0], it[-1]
    mid = it[1:-1]
    d.fit_text(60, top + 14, W - 120, 80, [runs_of(pre)] + [runs_of(x) for x in mid], 24, 12, spacing=120)
    for k in range(2):
        d.rect(W / 2 - 20, top + 100 + k * 16, 40, 20, NAVY, shape='CHEVRON', rot=90, role='形')
    d.rect(110, top + 150, W - 220, 100, WHITE, shadow=True, role='箱')
    d.fit_text(120, top + 150, W - 240, 100, [runs_of(ans)], 30, 13, role='箱の文字')


def r_card(d, s):
    top = d.bands(s.get('label'))
    it = s['items']
    head, cards = it[0], [split_kv(x) for x in it[1:]][:6]
    d.fit_text(30, top + 6, W - 60, 40, [runs_of(head)], 22, 12)
    n = len(cards)
    cols = 2 if n in (2, 4) else (3 if n >= 3 else n)
    rows = (n + cols - 1) // cols
    cw = (W - 60 - (cols - 1) * 14) / cols
    ch = (H - top - BAND - 64 - (rows - 1) * 12) / rows
    for k, (name, desc) in enumerate(cards):
        x = 30 + (k % cols) * (cw + 14)
        y = top + 52 + (k // cols) * (ch + 12)
        d.rect(x, y, cw, ch, WHITE, line=NAVY, lw=1.2, shadow=True, role='箱')
        hh = min(46, ch * 0.42)
        d.rect(x, y, cw, hh, NAVY, role='形')
        d.fit_text(x + 4, y, cw - 8, hh, [[(name, 'w')]], 17, 9, color=WHITE, role='箱の文字')
        if desc:
            isz = min(34, (ch - hh) * 0.5)
            d.icon(icon_for(name + desc), x + 10, y + hh + (ch - hh - isz) / 2, isz)
            d.fit_text(x + isz + 14, y + hh + 2, cw - isz - 20, ch - hh - 6, [runs_of(desc, False)], 15, 8, role='箱の文字', spacing=120)


def r_kazu(d, s):
    top = d.bands(s.get('label'))
    it = s['items']
    pre = it[0] if len(it) >= 3 else ''
    num = it[1] if len(it) >= 3 else it[0]
    unit = it[2] if len(it) >= 3 else (it[1] if len(it) > 1 else '')
    post = it[3] if len(it) >= 4 else ''
    if pre:
        d.fit_text(60, top + 22, W - 120, 50, [runs_of(pre, False)], 26, 12)
    # 数字と単位を1つの箱に（数字は大きい赤・単位は紺）
    numsz, usz = 96, 40
    tw = text_w(num, numsz, 900) + text_w(unit, usz, 700)
    while tw > W - 160 and numsz > 40:
        numsz -= 4; usz = max(20, usz - 2); tw = text_w(num, numsz, 900) + text_w(unit, usz, 700)
    y = top + 80
    hh = numsz * LH + 2 * PAD
    d.text(60, y, W - 120, hh, [[(num, 'r'), (unit, 'n')]], numsz, wt=900, role='数字')
    # 単位だけ小さく
    d.reqs.append({'updateTextStyle': {'objectId': d.layout[-1]['objs'][-1]['id'], 'textRange': {'type': 'FIXED_RANGE', 'startIndex': len(num), 'endIndex': len(num) + len(unit)},
                   'fields': 'fontSize', 'style': {'fontSize': pt(usz)}}})
    d.layout[-1]['objs'][-1]['unit_size'] = usz
    if post:
        d.fit_text(60, y + hh + 6, W - 120, 60, [runs_of(post, False)], 24, 12)


def r_shashin(d, s):
    d.slide('bg_gold.jpg')
    top = d.bands(None)
    it = s['items']
    hito = s.get('hito')
    lines = [runs_of(x) for x in it]
    if hito == 'なし':
        d.fit_text(50, 50, W - 100, H - 100, lines, 36, 14, spacing=135)
    else:
        d.fit_text(50, 36, W - 100, 150, lines, 34, 14, spacing=135)
        mood = '成功' if hito in (None, 'auto') else hito
        d.put(d.pick_hito(mood), W / 2 - 70, 190, 190, maxw=150)
        d.put(d.pick_hito(mood), W / 2 + 70, 190, 190, maxw=150)


def r_kurai(d, s):
    d.slide('bg_dark.jpg')
    it = s['items']
    d.rect(0, 140, W, 125, WHITE, role='箱')
    d.fit_text(40, 140, W - 80, 125, [runs_of(x) for x in it], 34, 14, role='箱の文字', spacing=125)


def r_marker(d, s):
    top = d.bands(s.get('label'))
    it = s['items']
    pre = it[:-1]
    last = it[-1]
    if pre:
        d.fit_text(60, top + 40, W - 120, 90, [runs_of(x) for x in pre], 26, 12, spacing=125)
    y = top + (150 if pre else 110)
    t = plain(last)
    sz, _ = fit([[(t, 'r')]], W - 160, 80, 36, 14)
    tw = text_w(t, sz) + 2 * PAD + 24
    d.rect(W / 2 - tw / 2, y, tw, sz * LH + 2 * PAD, GOLDBOX, role='マーカー')
    d.text(W / 2 - tw / 2, y, tw, sz * LH + 2 * PAD, [[(t, 'r')]], sz, role='箱の文字')


RENDER = {'message': None, '待機': r_taiki, 'hyoushi': r_hyoushi, 'tobira': r_tobira, '問い': r_toi, '悩み': r_nayami,
          '比較': r_hikaku, '等式': lambda d, s: r_hikaku(d, s, True), '番号': r_bangou, '流れ': r_nagare, 'nagare': r_nagare,
          '矢印': r_yajirushi, 'カード': r_card, '数字': r_kazu, '写真': r_shashin, '暗い': r_kurai, 'マーカー': r_marker}
NEEDS_GRID = {'message', '問い', '悩み', '比較', '等式', '番号', '流れ', 'nagare', '矢印', 'カード', '数字', 'マーカー'}


KATA_MODE = False   # True で、手本の Google スライドの型（層の作り）を写して作る（kata.py）


def render(d, s):
    k = s['kind']
    if KATA_MODE and k not in ('hyoushi', 'tobira', '待機'):
        import kata
        recent = [o.get('kata') for o in d.layout[-3:] if o.get('kata')]
        kk, us = kata.choose(s, s.get('_pos', 0.5), recent, d)
        if kk:
            kata.render(d, s, kk, us)
            d.layout[-1]['kind'] = k
            return
    if k in NEEDS_GRID:
        d.slide('bg_grid.png')
    fn = RENDER.get(k)
    if fn is None:
        if k not in ('message',):
            print('知らない型（普通の1メッセージで作る）:', k, file=sys.stderr)
        r_message(d, s)
    else:
        fn(d, s)
    d.layout[-1]['kind'] = k


# ---------- Drive ----------
def services():
    from googleapiclient.discovery import build
    from settei import creds
    c = creds(['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations'])
    return build('drive', 'v3', credentials=c, cache_discovery=False), build('slides', 'v1', credentials=c, cache_discovery=False)


def find_or_make(drv, parent, name):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and '{parent}' in parents and trashed=false"
    r = drv.files().list(corpora='drive', driveId=DRIVE, includeItemsFromAllDrives=True, supportsAllDrives=True, q=q, fields='files(id)').execute()['files']
    if r:
        return r[0]['id']
    return drv.files().create(body={'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent]},
                              supportsAllDrives=True, fields='id').execute()['id']


def upload_assets(drv, folder, keys):
    from googleapiclient.http import MediaFileUpload
    cache_f = os.path.join(A, 'drive_ids.json')
    cache = json.load(open(cache_f)) if os.path.exists(cache_f) else {}
    ids = {}
    for k in sorted(keys):
        p = os.path.join(A, k)
        h = hashlib.md5(open(p, 'rb').read()).hexdigest()
        c = cache.get(k)
        if c and c['md5'] == h and c.get('folder') == folder:
            try:
                drv.files().get(fileId=c['id'], supportsAllDrives=True, fields='id,trashed').execute()
                ids[k] = c['id']
                continue
            except Exception:
                pass
        fid = drv.files().create(body={'name': k.replace('/', '__'), 'parents': [folder]}, media_body=MediaFileUpload(p, resumable=False),
                                 supportsAllDrives=True, fields='id').execute()['id']
        cache[k] = {'id': fid, 'md5': h, 'folder': folder}
        ids[k] = fid
    json.dump(cache, open(cache_f, 'w'), ensure_ascii=False, indent=0)
    return ids


def retry(fn, n=6):
    for t in range(n):
        try:
            return fn()
        except Exception:
            if t == n - 1:
                raise
            time.sleep(5 * (t + 1))


def wait_public(U, log=print, limit=300):
    """フォルダの公開が中のファイルに届くまで待つ（届く前に入れると「画像を取れない」で落ちる）"""
    import subprocess, concurrent.futures as cf

    def ok(u):
        r = subprocess.run(['curl', '-s', '-L', '-o', '/dev/null', '-w', '%{http_code} %{content_type}', u], capture_output=True, text=True).stdout
        return r.startswith('200') and 'image' in r
    t0 = time.time()
    rest = list(U.values())
    while rest and time.time() - t0 < limit:
        with cf.ThreadPoolExecutor(8) as ex:
            res = list(ex.map(ok, rest))
        rest = [u for u, g in zip(rest, res) if not g]
        if rest:
            time.sleep(10)
    log(f'公開の確認: {len(U) - len(rest)}/{len(U)} 点が取れる（{int(time.time() - t0)}秒）')


def used_keys(slides):
    """一度だけ空回しで作って、使う素材の名前を集める（使う物だけ上げる）"""
    class Fake(dict):
        def __missing__(self, k):
            return 'x'
    keys = asset_keys()
    d = Deck(None, 'x', Fake(), {k: ratio(k) for k in keys if k.startswith(('soco/', 'icon/', 'deco/'))})
    for i, s in enumerate(slides):
        s['_pos'] = s.get('_pos', i / max(1, len(slides)))
        render(d, s)
    return sorted({o['bg'] for o in d.layout} | {ob['key'] for o in d.layout for ob in o['objs'] if ob.get('key')})


def ratio(key):
    from PIL import Image
    w, h = Image.open(os.path.join(A, key)).size
    return w / h


def asset_keys():
    ks = ['bg_grid.png', 'bg_cover.jpg', 'bg_gold.jpg', 'bg_dark.jpg', 'bg_navy.png']
    ks += [f'soco/{f}' for f in os.listdir(os.path.join(A, 'soco')) if f.endswith('.png')]
    ks += [f'icon/{f}' for f in os.listdir(os.path.join(A, 'icon')) if f.endswith('.png')]
    ks += [f'deco/{f}' for f in os.listdir(os.path.join(A, 'deco')) if f.endswith('.png')]
    return ks


def build_deck(md_path, pres=None, folder_name=FOLDER_NAME, title=None, log=print):
    meta, slides = parse(open(md_path).read())
    title = title or meta.get('title') or os.path.splitext(os.path.basename(md_path))[0]
    drv, sl = services()
    folder = find_or_make(drv, DRIVE, folder_name)
    sozai = find_or_make(drv, folder, '素材（作業用）')
    keys = used_keys(slides)
    # 空回しと本番で選ぶ絵がずれることがある（10/21 3本とも KeyError で止まった）。人物・アイコン・背景は全部上げておく
    keys = set(keys) | {k for k in asset_keys() if not k.startswith('deco/g_')}
    ids = upload_assets(drv, sozai, keys)
    perm = None
    try:
        # 画像を入れる間だけ、素材のフォルダ（素材サイトの絵とアイコンだけが入っている）に「リンクを知っている人は閲覧」を付ける。
        # 中のファイルに引き継がれる。終わったら finally で必ず外し、残っていないか数える
        perm = retry(lambda: drv.permissions().create(fileId=sozai, body={'type': 'anyone', 'role': 'reader'}, supportsAllDrives=True, fields='id').execute()['id'])
        U = {k: f'https://drive.google.com/uc?export=download&id={i}' for k, i in ids.items()}
        wait_public(U, log)
        R = {k: ratio(k) for k in asset_keys() if k.startswith(('soco/', 'icon/', 'deco/'))}
        if pres:
            old = sl.presentations().get(presentationId=pres).execute().get('slides', [])
            first = old[0]['objectId'] if old else None
            rest = [s['objectId'] for s in old[1:]]
            for k in range(0, len(rest), 400):
                sl.presentations().batchUpdate(presentationId=pres, body={'requests': [{'deleteObject': {'objectId': o}} for o in rest[k:k + 400]]}).execute()
            pid = pres
        else:
            pid = drv.files().create(body={'name': title, 'mimeType': 'application/vnd.google-apps.presentation', 'parents': [folder]},
                                     supportsAllDrives=True, fields='id').execute()['id']
            first = sl.presentations().get(presentationId=pid).execute()['slides'][0]['objectId']
        d = Deck(sl, pid, U, R)
        a0, a1 = float(meta.get('kata_kara', 0)), float(meta.get('kata_made', 1))   # 手本のどのあたりの型を使うか（0〜1）
        for i, s in enumerate(slides, 1):
            s['_pos'] = a0 + (a1 - a0) * (i - 1) / max(1, len(slides))
            render(d, s)
            if len(d.reqs) > 1800:
                d.flush()
                log(f'  {i}/{len(slides)} 枚')
        if first:
            d.reqs.append({'deleteObject': {'objectId': first}})
        d.flush()
    finally:
        # 作る途中で落ちても公開を残さない：フォルダと中のファイルを全部見て、公開を外す
        for fid in [sozai] + list(ids.values()):
            ps = retry(lambda: drv.permissions().list(fileId=fid, supportsAllDrives=True, fields='permissions(id,type)').execute()['permissions'])
            for p in ps:
                if p['type'] in ('anyone', 'domain'):
                    retry(lambda: drv.permissions().delete(fileId=fid, permissionId=p['id'], supportsAllDrives=True).execute())
        left = [fid for fid in [sozai] + list(ids.values())
                if any(p['type'] in ('anyone', 'domain') for p in retry(lambda: drv.permissions().list(fileId=fid, supportsAllDrives=True, fields='permissions(type)').execute()['permissions']))]
        log(f'公開の残り: {len(left)} 件（素材 {len(ids)} 点とフォルダを数えた）')
    out = {'title': title, 'presentation': pid, 'url': f'https://docs.google.com/presentation/d/{pid}/edit', 'slides': len(slides),
           'kinds': {k: sum(1 for s in slides if s['kind'] == k) for k in sorted({s['kind'] for s in slides})}}
    lay = os.path.splitext(md_path)[0] + '.layout.json'
    json.dump({'meta': out, 'layout': d.layout}, open(lay, 'w'), ensure_ascii=False)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('md')
    ap.add_argument('--pres')
    ap.add_argument('--plan', action='store_true')
    ap.add_argument('--folder', default=FOLDER_NAME)
    ap.add_argument('--title')
    ap.add_argument('--kata', action='store_true', help='手本の Google スライドの型（層）を写して作る')
    a = ap.parse_args()
    if a.plan:
        meta, slides = parse(open(a.md).read())
        kinds = {}
        for s in slides:
            kinds[s['kind']] = kinds.get(s['kind'], 0) + 1
        print(json.dumps({'title': meta.get('title'), 'slides': len(slides), 'kinds': kinds}, ensure_ascii=False, indent=1))
        return
    global KATA_MODE
    KATA_MODE = a.kata
    print(json.dumps(build_deck(a.md, a.pres, a.folder, a.title), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
