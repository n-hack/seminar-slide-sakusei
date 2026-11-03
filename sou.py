#!/usr/bin/env python3
"""手本（presentations.get の JSON）と、同じ資料の PPTX 書き出しを突き合わせて、1ページずつ「層の記録」を作る。

なぜ2つ使うか
  API の JSON … 文字（中身・字の大きさ・色・太さ・行間・揃え）と、置き場所（変形）は正確。
                 ただし「絵で塗った形」「グラデーション」「自由な形の線」は塗りが空 {} で返る（12746 部品中 7952）
  PPTX ………… その空の塗りの正体（画像・グラデーション・パス）が全部入っている
  両方とも部品の並び（重なり順）が同じ（867 ページ全部で数が一致・2026-11-01 実測）なので、順番で結べる

使い方
  python3 sou.py <raw/deck.json> <pptx を展開したフォルダ> <出す先>
    出す先/pNNN.json … 1ページの層（下から上の順）
    出す先/media.json … 画像ファイルごとの md5・大きさ・使われた回数
層の種類（kind）
  group 束ね ／ text 文字（形の塗りがあれば fill も持つ）／ shape 形（四角など API で作れる形）
  pic 画像（API の image）／ blip 画像で塗った四角 ／ vec 自由な形（単色かグラデーション・パスつき）
  line 線 ／ video 動画
"""
import json, os, sys, hashlib, collections
from lxml import etree

EMU = 12700.0
NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
A = '{%s}' % NS['a']
R_EMBED = '{%s}embed' % NS['r']


def emu(v):
    if not v:
        return 0.0
    m = v.get('magnitude', 0.0)
    return m / EMU if v.get('unit', 'EMU') == 'EMU' else m


def mat(t):
    """API の変形 → [a, b, tx(pt), c, d, ty(pt)]。0 の欄は返ってこない（proto3）ので、無い欄は 0"""
    if not t:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    k = EMU if t.get('unit', 'EMU') == 'EMU' else 1.0
    return [t.get('scaleX', 0.0), t.get('shearX', 0.0), t.get('translateX', 0.0) / k,
            t.get('shearY', 0.0), t.get('scaleY', 0.0), t.get('translateY', 0.0) / k]


def mul(a, b):
    return [a[0] * b[0] + a[1] * b[3], a[0] * b[1] + a[1] * b[4], a[0] * b[2] + a[1] * b[5] + a[2],
            a[3] * b[0] + a[4] * b[3], a[3] * b[1] + a[4] * b[4], a[3] * b[2] + a[4] * b[5] + a[5]]


def bbox(m, w, h):
    pts = [(m[0] * x + m[1] * y + m[2], m[3] * x + m[4] * y + m[5]) for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2)]


def rgb(c, scheme):
    """API の色（rgbColor / themeColor）→ #RRGGBB"""
    if not c:
        return None
    if 'themeColor' in c:
        c = scheme.get(c['themeColor'], {})
    else:
        c = c.get('rgbColor', c)
    return '#%02X%02X%02X' % tuple(int(round(c.get(k, 0.0) * 255)) for k in ('red', 'green', 'blue'))


def x_color(node):
    """PPTX の srgbClr（alpha つき）→ (#RRGGBB, alpha)"""
    if node is None:
        return None, 1.0
    s = node.find(A + 'srgbClr')
    if s is None:
        s = node.find(A + 'schemeClr')
        if s is None:
            return None, 1.0
        val = '#' + {'lt1': 'FFFFFF', 'dk1': '000000'}.get(s.get('val'), '000000')
    else:
        val = '#' + s.get('val').upper()
    al = s.find(A + 'alpha')
    return val, (int(al.get('val')) / 100000.0 if al is not None else 1.0)


def x_fill(sppr):
    """spPr の塗り → dict"""
    if sppr is None:
        return None
    b = sppr.find(A + 'blipFill')
    if b is not None:
        bl = b.find(A + 'blip')
        am = bl.find(A + 'alphaModFix') if bl is not None else None
        sr = b.find(A + 'srcRect')
        fr = b.find('.//' + A + 'fillRect')
        return {'type': 'blip', 'rid': bl.get(R_EMBED) if bl is not None else None,
                'alpha': (int(am.get('amt')) / 100000.0 if am is not None and am.get('amt') else 1.0),
                'src': {k: int(sr.get(k, 0)) / 100000.0 for k in 'lrtb'} if sr is not None else None,
                'fillRect': {k: int(fr.get(k, 0)) / 100000.0 for k in 'lrtb'} if fr is not None and any(fr.get(k) not in (None, '0') for k in 'lrtb') else None}
    g = sppr.find(A + 'gradFill')
    if g is not None:
        stops = []
        for gs in g.findall('.//' + A + 'gs'):
            c, al = x_color(gs)
            stops.append({'pos': int(gs.get('pos')) / 100000.0, 'color': c, 'alpha': al})
        lin = g.find(A + 'lin')
        path = g.find(A + 'path')
        out = {'type': 'grad', 'stops': stops}
        if lin is not None:
            out['angle'] = int(lin.get('ang', 0)) / 60000.0
        if path is not None:
            out['path'] = path.get('path')
            ftr = path.find(A + 'fillToRect')
            out['fillToRect'] = {k: int(ftr.get(k, 0)) / 100000.0 for k in 'lrtb'} if ftr is not None else None
        return out
    s = sppr.find(A + 'solidFill')
    if s is not None:
        c, al = x_color(s)
        return {'type': 'solid', 'color': c, 'alpha': al}
    return None


def x_line(sppr):
    ln = sppr.find(A + 'ln') if sppr is not None else None
    if ln is None or ln.find(A + 'noFill') is not None:
        return None
    s = ln.find(A + 'solidFill')
    if s is None:
        return None
    c, al = x_color(s)
    return {'color': c, 'alpha': al, 'w': int(ln.get('w', 12700)) / EMU}


def x_path(cg):
    """custGeom → [{'w','h','cmds':[(op,[(x,y),..])]}]"""
    out = []
    for p in cg.findall('.//' + A + 'path'):
        cmds = []
        for c in p:
            op = etree.QName(c).localname
            pts = [(int(pt.get('x')), int(pt.get('y'))) for pt in c.findall(A + 'pt')]
            cmds.append((op, pts))
        out.append({'w': int(p.get('w', 0)), 'h': int(p.get('h', 0)), 'fill': p.get('fill'), 'stroke': p.get('stroke'), 'cmds': cmds})
    return out


def x_flat(tree):
    out = []

    def w(node):
        for c in node:
            tag = etree.QName(c).localname
            if tag in ('sp', 'pic', 'cxnSp', 'graphicFrame', 'grpSp'):
                out.append(c)
                if tag == 'grpSp':
                    w(c)
    w(tree.find('.//p:cSld/p:spTree', NS))
    return out


def x_bg(tree):
    bg = tree.find('.//p:cSld/p:bg/p:bgPr', NS)
    return x_fill(bg) if bg is not None else None


def text_of(sh, scheme):
    t = sh.get('text')
    if not t:
        return None
    paras, runs = [], []
    for te in t['textElements']:
        if 'paragraphMarker' in te:
            st = te['paragraphMarker'].get('style', {})
            paras.append({'start': te.get('startIndex', 0), 'end': te['endIndex'],
                          'align': st.get('alignment'), 'lineSpacing': st.get('lineSpacing'),
                          'spaceAbove': emu(st.get('spaceAbove')), 'spaceBelow': emu(st.get('spaceBelow')),
                          'indentStart': emu(st.get('indentStart')), 'indentEnd': emu(st.get('indentEnd')),
                          'indentFirstLine': emu(st.get('indentFirstLine')), 'spacingMode': st.get('spacingMode'),
                          'bullet': bool(te['paragraphMarker'].get('bullet'))})
            bu = te['paragraphMarker'].get('bullet') or {}
            if bu.get('glyph'):   # 手本の記号そのもの（• など）と記号の字の形
                bs = bu.get('bulletStyle', {})
                wf = bs.get('weightedFontFamily', {})
                paras[-1]['glyph'] = bu['glyph']
                paras[-1]['glyph_style'] = {'font': wf.get('fontFamily', bs.get('fontFamily')), 'weight': wf.get('weight', 700 if bs.get('bold') else 400),
                                            'size': round(emu(bs.get('fontSize')), 2) if bs.get('fontSize') else None,
                                            'color': rgb(bs.get('foregroundColor', {}).get('opaqueColor'), scheme), 'bold': bs.get('bold', False)}
        elif 'textRun' in te:
            st = te['textRun'].get('style', {})
            fc = st.get('foregroundColor', {}).get('opaqueColor')
            bc = st.get('backgroundColor', {}).get('opaqueColor')
            wf = st.get('weightedFontFamily', {})
            runs.append({'start': te.get('startIndex', 0), 'end': te['endIndex'], 'text': te['textRun']['content'],
                         'font': wf.get('fontFamily', st.get('fontFamily')), 'weight': wf.get('weight', 700 if st.get('bold') else 400),
                         'size': round(emu(st.get('fontSize')), 2) if st.get('fontSize') else None,
                         'color': rgb(fc, scheme), 'bg': rgb(bc, scheme) if bc else None,
                         'bold': st.get('bold', False), 'italic': st.get('italic', False), 'underline': st.get('underline', False),
                         'strike': st.get('strikethrough', False), 'baseline': st.get('baselineOffset', 'NONE'),
                         'link': st.get('link')})
    full = ''.join(r['text'] for r in runs)
    return {'content': full, 'paras': paras, 'runs': runs, 'lists': bool(t.get('lists'))}


def build_page(slide, xtree, rels, scheme, media_dir):
    flat_api = []

    def walk(els, parent_m, gid, depth):
        for e in els:
            m = mul(parent_m, mat(e.get('transform')))
            flat_api.append((e, m, gid, depth))
            if 'elementGroup' in e:
                walk(e['elementGroup']['children'], m, e['objectId'], depth + 1)
    walk(slide.get('pageElements', []), [1, 0, 0, 0, 1, 0], None, 0)
    xs = x_flat(xtree)
    assert len(xs) == len(flat_api), (slide['objectId'], len(xs), len(flat_api))
    layers = []
    for z, ((e, m, gid, depth), x) in enumerate(zip(flat_api, xs)):
        w, h = emu(e.get('size', {}).get('width')), emu(e.get('size', {}).get('height'))
        L = {'id': e['objectId'], 'z': z, 'group': gid, 'depth': depth, 'w': round(w, 3), 'h': round(h, 3),
             'm': [round(v, 6) for v in m], 'box': bbox(m, w, h)}
        tag = etree.QName(x).localname
        sppr = x.find('p:spPr', NS) if tag in ('sp', 'cxnSp') else x.find('p:spPr', NS)
        if 'elementGroup' in e:
            L['kind'] = 'group'
            L['children'] = [c['objectId'] for c in e['elementGroup']['children']]
        elif 'image' in e:
            L['kind'] = 'pic'
            bf = x.find('p:blipFill', NS)
            if bf is not None:
                bl = bf.find(A + 'blip')
                am = bl.find(A + 'alphaModFix') if bl is not None else None
                sr = bf.find(A + 'srcRect')
                L['fill'] = {'type': 'blip', 'rid': bl.get(R_EMBED), 'alpha': (int(am.get('amt')) / 100000.0 if am is not None and am.get('amt') else 1.0),
                             'src': {k: int(sr.get(k, 0)) / 100000.0 for k in 'lrtb'} if sr is not None else None}
            L['crop'] = e['image'].get('imageProperties', {}).get('cropProperties')
        elif 'line' in e:
            L['kind'] = 'line'
            lp = e['line'].get('lineProperties', {})
            L['line'] = {'weight': emu(lp.get('weight')), 'dash': lp.get('dashStyle'), 'start': lp.get('startArrow'), 'end': lp.get('endArrow'),
                         'color': rgb(lp.get('lineFill', {}).get('solidFill', {}).get('color'), scheme),
                         'alpha': lp.get('lineFill', {}).get('solidFill', {}).get('alpha', 1.0), 'category': e['line'].get('lineCategory'),
                         'type': e['line'].get('lineType')}
        elif 'video' in e:
            L['kind'] = 'video'
            L['video'] = {'source': e['video'].get('source'), 'id': e['video'].get('id'), 'props': e['video'].get('videoProperties')}
        elif 'shape' in e:
            sh = e['shape']
            sp = sh.get('shapeProperties', {})
            st = sh.get('shapeType')
            cg = sppr.find(A + 'custGeom') if sppr is not None else None
            xf = x_fill(sppr)
            api_fill = sp.get('shapeBackgroundFill', {})
            if xf and xf['type'] == 'blip':
                L['kind'] = 'blip'
                L['fill'] = xf
            elif cg is not None and xf and xf['type'] in ('solid', 'grad'):
                L['kind'] = 'vec'
                L['fill'] = xf
                L['path'] = x_path(cg)
            else:
                L['kind'] = 'shape'
                L['shapeType'] = st
                if api_fill.get('propertyState') != 'NOT_RENDERED' and api_fill.get('solidFill'):
                    sf = api_fill['solidFill']
                    L['fill'] = {'type': 'solid', 'color': rgb(sf.get('color'), scheme), 'alpha': sf.get('alpha', 1.0)}
                elif xf:
                    L['fill'] = xf
                if cg is not None:
                    L['path'] = x_path(cg)
            ol = sp.get('outline', {})
            if ol.get('propertyState') not in ('NOT_RENDERED',) and ol.get('outlineFill'):
                sf = ol['outlineFill'].get('solidFill', {})
                L['outline'] = {'color': rgb(sf.get('color'), scheme), 'alpha': sf.get('alpha', 1.0), 'w': emu(ol.get('weight')), 'dash': ol.get('dashStyle')}
            else:
                xl = x_line(sppr)
                if xl:
                    L['outline'] = xl
            L['contentAlignment'] = sp.get('contentAlignment')
            L['autofit'] = sp.get('autofit', {}).get('autofitType')
            tx = text_of(sh, scheme)
            if tx and tx['content'].strip():
                L['text'] = tx
                bp = x.find('.//' + A + 'bodyPr')
                if bp is not None:
                    L['inset'] = {k: int(bp.get(k + 'Ins', 91440 if k in 'lr' else 45720)) / EMU for k in 'lrtb'}
                    L['wrap'] = bp.get('wrap')
                    L['vert'] = bp.get('vert')
                if L['kind'] == 'shape':
                    L['kind'] = 'text'
            lk = sp.get('link')
            if lk:
                L['link'] = lk
        else:
            L['kind'] = 'other'
        fl = L.get('fill')
        if fl and fl.get('type') == 'blip':
            fl['media'] = os.path.basename(rels.get(fl.pop('rid', None), '')) or None
        layers.append(L)
    pp = slide.get('pageProperties', {}).get('pageBackgroundFill', {})
    bg = None
    if pp.get('solidFill'):
        bg = {'type': 'solid', 'color': rgb(pp['solidFill'].get('color'), scheme), 'alpha': pp['solidFill'].get('alpha', 1.0)}
    else:
        xb = x_bg(xtree)
        if xb:
            if xb.get('type') == 'blip':
                xb['media'] = os.path.basename(rels.get(xb.pop('rid', None), ''))
            bg = xb
    return {'id': slide['objectId'], 'bg': bg, 'layers': layers}


def main():
    deck_f, xdir, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    d = json.load(open(deck_f))
    scheme = {c['type']: c.get('color', {}) for c in d['masters'][0]['pageProperties']['colorScheme']['colors']}
    pres = etree.parse(os.path.join(xdir, 'ppt/presentation.xml'))
    rr = etree.parse(os.path.join(xdir, 'ppt/_rels/presentation.xml.rels')).getroot()
    rm = {r.get('Id'): r.get('Target') for r in rr}
    order = [rm[s.get('{%s}id' % NS['r'])] for s in pres.findall('.//p:sldIdLst/p:sldId', NS)]
    media_use = collections.Counter()
    for i, (s, f) in enumerate(zip(d['slides'], order), 1):
        xf = os.path.join(xdir, 'ppt', f)
        rf = os.path.join(os.path.dirname(xf), '_rels', os.path.basename(xf) + '.rels')
        rels = {r.get('Id'): r.get('Target') for r in etree.parse(rf).getroot()} if os.path.exists(rf) else {}
        pg = build_page(s, etree.parse(xf), rels, scheme, os.path.join(xdir, 'ppt/media'))
        pg['page'] = i
        for L in pg['layers']:
            if L.get('fill', {}) and L['fill'].get('media'):
                media_use[L['fill']['media']] += 1
        json.dump(pg, open(os.path.join(out, f'p{i:03d}.json'), 'w'), ensure_ascii=False)
    from PIL import Image
    md = {}
    mdir = os.path.join(xdir, 'ppt/media')
    for f in sorted(os.listdir(mdir)):
        p = os.path.join(mdir, f)
        im = Image.open(p)
        md[f] = {'md5': hashlib.md5(open(p, 'rb').read()).hexdigest(), 'size': im.size, 'mode': im.mode, 'bytes': os.path.getsize(p), 'uses': media_use.get(f, 0)}
    json.dump(md, open(os.path.join(out, 'media.json'), 'w'), ensure_ascii=False, indent=0)
    print(len(d['slides']), 'ページ', sum(media_use.values()), '回の画像使用', len(md), '画像ファイル')


if __name__ == '__main__':
    main()
