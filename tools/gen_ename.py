# -*- coding: utf-8 -*-
"""
从 UI 工程 .json 直接算出控件 ID，生成/校验 ename.h(= apps 侧的 style_JL_new.h)。

为什么要这个：UITools 是 GUI，只有人工点「保存/生成」才会吐 ename.h。
改完 json 就想接着写应用代码时，用这个先把 ID 算出来，不用等导出。
ID 规则见 jlui.py 抬头，已用仓库里两个工程逐个标定过。

    python gen_ename.py <工程.json>                 # 打印 ename.h 内容
    python gen_ename.py <工程.json> -o ename.h      # 写文件
    python gen_ename.py <工程.json> --check <参考.h> # 和已有头文件比对，有差异返回 1

--check 的典型用法(改完 json、还没导出资源时自查)：

    python gen_ename.py 模式界面/project/SmallColorTFT.json \
        --check ../../../../../apps/soundbox/include/ui/style_JL_new.h

⚠ 只有 ID 是算得出来的。图片索引(result_pic_index.h)、字符串索引
(result_str_index.h)、UI_VERSION 都由 ResBuilder 在打包时算，
这里算不出，--check 会跳过它们。
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jlui import (setup_stdout, load, build_ids, parse_ename_h,
                  TYPENAME, typecode, ename_of, iter_pages, page_nodes)


def render(ids, extra=None):
    lines = ['#ifndef UI_TOOL_ENAME', '#define UI_TOOL_ENAME', '']
    for k in sorted(ids):
        lines.append('#define %s 0X%X' % (k, ids[k]))
    # 工程级宏：UI_ROTATE 是工具里设的屏幕旋转角，UI_VERSION 是资源版本哈希，
    # 两个都不是控件 ID，算不出来，只能从已有头文件里继承。
    for k in sorted(extra or {}):
        lines.append('#define %s 0X%X' % (k, extra[k]))
    lines += ['', '#endif', '']
    return '\n'.join(lines)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('-o', '--out')
    ap.add_argument('--check', metavar='ename.h')
    ap.add_argument('--prj', type=lambda s: int(s, 0), default=0,
                    help='工程号(UI 编译工具里设的，本仓库两个工程都是 0)')
    ap.add_argument('--list', action='store_true', help='按页列出控件，便于核对')
    args = ap.parse_args()

    doc = load(args.project)
    ids = build_ids(doc, args.prj)

    if args.list:
        for pi, page in iter_pages(doc):
            print('PAGE_%d  0X%X' % (pi, ids['PAGE_%d' % pi]))
            for node, depth, _p in page_nodes(page):
                tc = typecode(node)
                e = ename_of(node)
                if tc is None or not e:
                    continue
                print('  %s%-22s %-14s 0X%X' % ('  ' * depth, e.upper(),
                                                TYPENAME.get(tc, '?%d' % tc),
                                                ids[e.upper()]))
        return 0

    if args.check:
        ref = parse_ename_h(args.check)
        # 这两个不是控件 ID，比不了
        skip = {'UI_ROTATE', 'UI_VERSION'}
        ref_ids = {k: v for k, v in ref.items() if k not in skip}
        bad = [(k, ids[k], ref_ids[k]) for k in set(ids) & set(ref_ids)
               if ids[k] != ref_ids[k]]
        only_ref = sorted(set(ref_ids) - set(ids))
        only_new = sorted(set(ids) - set(ref_ids))
        print('工程 %s' % args.project)
        print('参考 %s' % args.check)
        print('  一致 %d, 不一致 %d, 只在参考里 %d, 只在工程里 %d'
              % (len(set(ids) & set(ref_ids)) - len(bad), len(bad),
                 len(only_ref), len(only_new)))
        for k, a, b in sorted(bad):
            print('  [ID 变了] %-26s 工程算出 0X%X, 头文件里是 0X%X' % (k, a, b))
        for k in only_ref:
            print('  [头文件多出] %-26s 0X%X  (工程里已删或改名, 应用代码可能还在用)'
                  % (k, ref_ids[k]))
        for k in only_new:
            print('  [工程新增] %-26s 0X%X  (导出后才会进头文件)' % (k, ids[k]))
        return 1 if (bad or only_ref or only_new) else 0

    extra = {}
    if args.out and os.path.exists(args.out):
        old = parse_ename_h(args.out)
        extra = {k: v for k, v in old.items() if k in ('UI_ROTATE', 'UI_VERSION')}
    text = render(ids, extra)
    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        print('已写 %s (%d 个 ID)' % (args.out, len(ids)))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
