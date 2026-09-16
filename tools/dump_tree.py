# -*- coding: utf-8 -*-
"""
把 UI 工程 .json 打成一棵可读的树。工程文件动辄几 MB，直接 grep 是看不懂结构的。

    python dump_tree.py <工程.json>              # 所有页的概览
    python dump_tree.py <工程.json> -p 4          # 只看第 4 页，带全部细节
    python dump_tree.py <工程.json> -p 4 --props  # 再加上每个控件的专有属性

    python dump_tree.py <工程.json> -p 4 -v      # 再加上 format/align/image-type 等

每行的信息：缩进=层级，ENAME(算出来的 ID)，类型，rect，以及
[hide]隐藏 / bg=背景色 / img=背景图 / imgs=图片张数 / str=文字条目。
加 -v 再多出 fmt=(Time/Number 的格式串) / align / type=(image-type) /
play=(轮播) / scroll=(列表滚动方式) —— 都是排版时要反复核对的。
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jlui import (setup_stdout, load, iter_pages, page_nodes, typecode, ename_of,
                  css_of, rect_of, color_format_of, prop_by_name, props,
                  TYPENAME, build_ids)

# 这些属性已经在主行里显示过了，细节行不再重复
SKIP_PROPS = {'id', 'element_css', 'luascript'}


def fmt_rect(r):
    if not r:
        return '?'
    return '%d,%d %dx%d' % (r['x'], r['y'], r['width'], r['height'])


def brief_prop(p):
    """把一条属性压成一行。值放在哪个键取决于 -type，所以挑已知的几个键找。"""
    n = p.get('-name')
    t = p.get('-type')
    for k in ('piclist', 'arrlist', 'list', 'value', 'default', 'text-str',
              'color', 'background-color', 'str'):
        if k in p:
            v = p[k]
            if isinstance(v, list):
                return '%s=%s' % (n, ('[%d项] ' % len(v)) + ', '.join(map(str, v[:4])))
            return '%s=%r' % (n, v)
    if t == 'action':
        acts = p.get('action') or []
        return 'action(%d)' % len(acts)
    return n


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('-p', '--page', type=int, help='只看这一页')
    ap.add_argument('--props', action='store_true', help='连控件专有属性一起打印')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='多显示排版要核对的几项：format / align / image-type / 轮播 / 滚动')
    ap.add_argument('--prj', type=lambda s: int(s, 0), default=0)
    args = ap.parse_args()

    doc = load(args.project)
    ids = build_ids(doc, args.prj)

    for pi, page in iter_pages(doc):
        if args.page is not None and pi != args.page:
            continue
        pr = rect_of(page)
        print('=== PAGE_%d  0X%X  %s  (%s)' % (pi, ids['PAGE_%d' % pi],
                                               fmt_rect(pr), page.get('caption')))
        for layer in page.get('layer', []) or []:
            print('    图层 color_format=%s' % color_format_of(layer))

        for node, depth, _parent in page_nodes(page):
            tc = typecode(node)
            e = ename_of(node)
            css = css_of(node)
            inv = css.get('invisible', {})
            hidden = str(inv.get('value', inv.get('default'))).lower() == 'true'

            tags = []
            if hidden:
                tags.append('[hide]')
            bg = (css.get('background_color', {}).get('background-color') or '').strip()
            if bg:
                tags.append('bg=%s' % bg)
            img = (css.get('background_image', {}).get('background-image') or '').strip()
            if img:
                tags.append('img=%s' % img.rsplit('/', 1)[-1])
            for pname, label in (('normal_image', 'imgs'), ('highlight_image', 'hl'),
                                 ('image', 'imgs'), ('charge_image', 'chg'),
                                 ('number', 'num'), ('delimiter', 'delim')):
                pi_ = prop_by_name(node, pname)
                if pi_ and pi_.get('list'):
                    tags.append('%s=%d' % (label, len(pi_['list'])))
            st = prop_by_name(node, 'str')
            if st and st.get('list'):
                tags.append('str=%s' % ','.join(map(str, st['list'][:4])))

            if args.verbose:
                # 排版时最常要核对的几项，平时不显示是因为一行放不下
                fmt = prop_by_name(node, 'format')
                if fmt and fmt.get('default'):
                    tags.append('fmt=%r' % fmt['default'])
                al = css.get('align', {})
                if al:
                    tags.append('align=%s' % str(al.get('value', al.get('default')))
                                .replace('ALIGN_', ''))
                for pname in ('normal_image', 'image', 'number'):
                    pi_ = prop_by_name(node, pname)
                    if pi_ and pi_.get('list'):
                        tags.append('type=%s' % (pi_.get('image-type') or '-'))
                        break
                pm = prop_by_name(node, 'play_mode')
                if pm and str(pm.get('default')) not in ('PLAY_NONE', 'None'):
                    iv = prop_by_name(node, 'interval')
                    tags.append('play=%s/%sms' % (pm['default'],
                                                  iv.get('default') if iv else '?'))
                sm = prop_by_name(node, 'scroll_mode')
                if sm:
                    tags.append('scroll=%s' % sm.get('default'))

            idtxt = '0X%X' % ids[e.upper()] if e and e.upper() in ids else '-'
            print('%s%-24s %-14s %-16s %s %s'
                  % ('  ' * (depth + 1), (e or node.get('-name') or ''),
                     TYPENAME.get(tc, '?'), fmt_rect(rect_of(node)), idtxt,
                     ' '.join(tags)))

            if args.props:
                for p in props(node):
                    if p.get('-name') in SKIP_PROPS:
                        continue
                    b = brief_prop(p)
                    if b:
                        print('%s· %s' % ('  ' * (depth + 3), b))
    return 0


if __name__ == '__main__':
    sys.exit(main())
