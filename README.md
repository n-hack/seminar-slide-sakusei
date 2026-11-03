# セミナースライド作成

手本にしたい Google スライド（セミナー資料）を1枚ずつ「層の作り」として学び、
同じ見た目のページを Google スライドに作り直す道具一式です。
学んだ型を使えば、一言の頼み（テーマ・相手・枚数）から新しいセミナースライドを作れます。

- 作る先は Google スライド（API で作るので、できた物はそのまま人が直せる）
- 画像を作る AI は使いません（AI の利用料はかかりません）。文は AI（Claude など）か人が書きます
- 867 ページの手本で、作り直し 866 枚が合格の線（後述）を通った道具です

## 中身

| 置き場 | 中身 |
|---|---|
| `*.py` | 道具（役目は下の表） |
| `settei.py` / `settei.example.env` | 設定。鍵の道・手本の ID などは全部環境変数で渡す |
| `assets/` | 背景4枚・線画アイコン（Material Symbols）・帯の飾り・人物素材の出どころ一覧（`soco/meta.json`） |
| `kata/` | 学んだ型の表の見本（手本の文は「〇」で伏せてある。箱の大きさ・字数・行数・字の大きさ・色・伝えたいことは残っている） |
| `docs/manabi.md` | 866 枚を作り直して分かった決まり・実験の記録 |
| `docs/rei-kousei.json` | 一言の頼みから作るときの構成の例 |

## 用意

1. Python 3.10 以上と、`pip install -r requirements.txt`
2. Google Cloud のサービスアカウントの鍵（JSON）。Google Slides API と Google Drive API を有効にする
   - 手本の資料をサービスアカウントのメールに「閲覧者」で共有する。作る先はサービスアカウントの Drive か、共有した資料
   - Google Workspace でドメイン全体の委任を使うなら `SLIDE_SUBJECT` に成り代わる人のメールを入れる（使わないなら空）
3. 日本語の字の形：Noto Sans JP（Google Fonts・SIL Open Font License）を `assets/NotoSansJP.ttf` に置くか、`SLIDE_FONT` で道を渡す
4. 人物の絵（使うときだけ）：`assets/soco/meta.json` の URL（ソコスト・無料素材）から手で取り、`assets/soco/<番号>.png`（線だけの版）・`assets/soco_color/<番号>.png`（色つき版）に置く。素材サイトの決まりで再配布はできないので、このリポジトリには入れていない
5. 設定を読み込む：`cp settei.example.env .env` → 値を入れて `set -a; source .env; set +a`（`.env` は `.gitignore` 済み）

### 環境変数

| 名前 | 中身 | 要るとき |
|---|---|---|
| `SLIDE_SA_KEY` | サービスアカウントの鍵（JSON）の道 | 必ず |
| `SLIDE_SUBJECT` | ドメイン全体の委任で成り代わる人のメール（空なら委任しない） | 委任を使うとき |
| `SLIDE_TEHON_ID` | 手本の Google スライドの ID（読むだけ） | 手本を学ぶとき・手本の画像を取るとき |
| `SLIDE_WORK` | 作業フォルダ（学んだ結果の置き場）。既定 `~/slide-work` | 必ず |
| `SLIDE_SHARE_TO` | 作った資料に編集権限を付ける相手のメール（空なら付けない） | 任意 |
| `SLIDE_DRIVE` | `make.py`（前の世代）が作る先の共有ドライブ ID | `make.py` を使うときだけ |
| `SLIDE_FONT` | 日本語の字の形（ttf）の道。既定 `assets/NotoSansJP.ttf` | 任意 |

道具の中には、鍵・ID・メール・決め打ちの道を1つも書いていません。全部ここから読みます。

## 使い方A：自分の手本を学ばせる

`W=$SLIDE_WORK`、`S=このリポジトリの道` とします。重い処理は `nice -n 19` で走らせます。

```bash
# 1. 手本を取り込む（読むだけ）
nice -n 19 python3 $S/tehon_get.py $W/raw                      # presentations.get → raw/deck.json・pNNN.json
#    Drive で手本を PPTX に書き出し、$W/pptx/x/ に展開しておく（画像は pptx/x/ppt/media/）
nice -n 19 python3 $S/sou.py $W/raw/deck.json $W/pptx/x $W/sou # 1ページずつ層の記録 sou/pNNN.json
nice -n 19 python3 $S/sa.py thumbs tehon $W/tehon-img          # 手本の画像（幅1600）

# 2. 型を作る
python3 $S/sozai_bunrui.py $W    # 手本の画像を6種類に分ける sozai/bunrui.json（おおよそ。違う物は手で直す）
python3 $S/mokuroku.py $W        # 大きな型（A〜J・その他）kata-index.json・kata.md（型の名前は kata-types.json を手で直す）
python3 $S/kata_zenbu.py $W      # 1ページ＝1型 kata-zenbu.json・kata-zenbu.md（伝えたいこと15種・連番の組）
python3 $S/kata_waku.py $W       # 型ごとの箱の上限（1行の字数 per・行数 gyou）kata-waku.json・kata-waku.md

# 3. 1ページ作り直して見比べる（作り直し先は試し用の資料）
python3 $S/fukusei.py new 試し用                                 # 新しい資料を作り presId を出す → $W/tameshi-pres.json に {"presentation": "<presId>"} で置く
T=$(python3 -c "import json;print(json.load(open('$W/tameshi-pres.json'))['presentation'])")
nice -n 19 python3 $S/fukusei.py build $T $W/sou $W/pptx/x/ppt/media 44   # 最後に「公開の残り 0 件」
OUT=/tmp/slide-tameshi-p044 && rm -rf $OUT
nice -n 19 python3 $S/sa.py thumbs $T $OUT/tmp 1
mkdir -p $OUT/img && mv $OUT/tmp/p001.png $OUT/img/p044.png
nice -n 19 python3 $S/sa.py diff $W/tehon-img $OUT/img $OUT/cmp 44:44     # 差の数字と左右に並べた画像

# 4. 全ページを周回で作り直して合否を数える（作り直し先は $W/pres.json）
nice -n 19 python3 $S/zenbu.py $W 10 > $W/zenbu.out 2>&1
touch $W/zenbu-tomeru            # 止めるときは札を置く（kill しない。一時公開が残る）
python3 $S/kekka_hyou.py $W      # ページごとの表
```

- build は資料の中身を全部消してから作る。作ったページは資料の1ページ目になる
- 試しには文字の多いページを選ぶ（絵だけのページはほぼ必ず通り、試しにならない）
- 手本と本番用の資料には書き込まない。作る先は試し用の資料か、新しく作る資料だけ

## 使い方B：一言の頼みから新しいスライドを作る

入口は `tsukuru.py` 1本。書くのは `kousei.json`（ページごとの伝えたいこと）と `daihon.json`（箱ごとの文）だけです。

```bash
OUT=~/slide-out/頼みごとの名前
python3 $S/tsukuru.py tsutae $W              # 伝えたいこと15種の一覧
# ① OUT/kousei.json を書く（例 docs/rei-kousei.json）
python3 $S/tsukuru.py erabu $W $OUT          # ② 型を選ぶ → OUT/waku.md（箱ごとの「◯字×◯行」）と daihon.json のひな形
# ③ waku.md を見て daihon.json の moji を埋める（箱の数・順は手本のまま。半角は0.5字で数える）
python3 $S/tsukuru.py mon $W $OUT            # ④ 文字数の門。止まったら文を短くする（上限は広げない）
nice -n 19 python3 $S/tsukuru.py tsukuru $W $OUT --pres <試し用か新しい資料のID>   # ⑤ 作る→画像→門→URL
```

- ⑤は 文字数の門 → `orijinaru.py` → `fukusei.py build`（同時に1本・メモリに余裕がある時だけ）→ 画像 → `kensa_ori.py`（はみ出し・重なり・字の小ささ・箱の余り・人物の大きさ）→ `narabe.jpg`（手本の同じ型と左右に並べた画像）→ API で枚数。全部合格で枚数が合ったときだけ URL を出す（`OUT/kekka.json`）
- URL を人に渡す前に `narabe.jpg` を必ず目で見る（門が見逃した物を探す）
- `--pres` を省くと新しい資料を作る

### `kata/` の見本だけで試すとき

`cp kata/* $SLIDE_WORK/` で、型の表（文は伏せ字）を作業フォルダに置けます。
②の型選びと④の文字数の門までは、この表だけで動きます（`waku.md` の「手本の文」は伏せ字の「〇」で出ます）。
⑤で実際に作るには、使い方Aで自分の手本を学んだ `sou/`（層の記録）と `pptx/x/ppt/media/`（手本の画像）が要ります。

## 合格の線

違う所（ratio）3% 以下 かつ ssim 0.985 以上（`sa.py diff` の値・800×450 で比べる）。

- mad … 画素の色の差の平均（0〜255）
- ratio … 色の差が 32 を超えた画素の割合（%）
- ssim … 形の似かた（1 が同じ）

## 守ること

- 手本には書き込まない（読むだけ）
- 素材の一時公開は作るたびに 0 件へ戻す（`fukusei.py` が最後に数えて「公開の残り 0 件」と出す。0 でなければ直す）
- 作り直し（`fukusei.py build`）は同時に1本だけ。鍵（`assets/fukusei_cache/build.lock`）で自動で順番待ちになる
- 周回は kill せず `zenbu-tomeru` の札で止める
- 重い処理は `nice -n 19`。macOS ではメモリの圧力（`sysctl -n kern.memorystatus_vm_pressure_level`）が 1 のときだけ始める（ほかの OS では見ずに進む）
- 読めない JPEG は macOS の `sips` で PNG に直して使う（`fukusei.py open_media`。ほかの OS では Pillow で開けない画像は飛ばす前に自分で PNG にする）

## 各 .py の役目

| 道具 | 役目 |
|---|---|
| settei.py | 環境変数から設定と Google の鍵を読む |
| tehon_get.py | 手本を読むだけ（presentations.get）→ raw/ |
| sou.py | 手本の JSON と PPTX を突き合わせ、1ページずつ層の記録 sou/pNNN.json を作る（箇条書きの記号も記録） |
| sozai_bunrui.py | 手本の画像を6種類（背景・帯・線画アイコン・イラスト・写真・単色）に分ける sozai/bunrui.json |
| mokuroku.py | 大きな型（A〜J・その他）の目録 kata-index.json・kata.md |
| kata_zenbu.py | 全ページを1型ずつ残す（伝えたいこと15種・連番の組・似せて続ける組） |
| kata_waku.py | 型ごとの箱の上限（per・gyou）・人物とアイコンの数の表 kata-waku.json／kata-waku.md |
| fukusei.py | 層の記録から Google スライドに同じページを作る（new／build／dry） |
| sa.py | 画像を取る（thumbs）・手本と作り直しの差を数える（diff） |
| shuu.py | 1周（作り直し→画像→差→kekka.json） |
| zenbu.py | 残りを1周10枚ずつ全部回す（圧力を見る・やり直し・止めの札） |
| kekka_hyou.py | kekka.json からページごとの最新の差と合否の表 |
| hako_zure.py | 文字の箱ごとのずれ（左右・上下）を測る（実験用） |
| narabe.py | 伝えたいことの並びから型を選んで並べる |
| orijinaru.py | 型だけを使って手本に無い文言のページを作る（人物は無料素材に差し替え・アイコンは線画アイコンの枠だけ） |
| tsukuru.py | 一言の頼みの入口（tsutae／erabu／mon／tsukuru） |
| kensa_ori.py | 新しく作ったページを画像で調べる門（はみ出し・重なり・字の小ささ・箱の余り・人物の大きさ） |
| make.py | 前の世代（台本 Markdown から作る）。いまは orijinaru.py・tsukuru.py が中の部品（字の幅・人物とアイコンの選び方）を使う。`--kata` の作り方は前の世代の道具が要るので、このリポジトリでは使わない |

決まりと実験の中身は `docs/manabi.md` にあります。
