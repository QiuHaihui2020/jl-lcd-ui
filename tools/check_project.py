# -*- coding: utf-8 -*-
"""
彩屏 UI 工程(.json)语义体检。有错误返回 1，只有提示返回 0。

    python check_project.py <工程.json> [--size 240x240]

查的都是 GUI 工具会放行、但要到写代码或上板才发现的东西：

  错误
    - 图层 color_format 不是 OSD16(彩屏走的是 OSD16 路径，OSD1 是单色点阵屏的)
    - ename 为空/重复/含非法字符(会被转成大写当宏名，只能是 [A-Za-z0-9_])
    - property 里缺 id 项
    - 认不出控件类型(caption 和 -type 都不在类型码表里 → 生成器给类型码 0)
    - rect 宽或高为 0
    - 页节点的 rect 不是裸对象(多带了 -name 键)
    - 组合控件(slider/vslider/watch/compass/progressbar)的零件 caption 被改过
    - 控件有两份 element_css，但两份除 background_color 外还有别的差异
      (第二份是高亮态，选中时整份换掉；rect 写错就是"选中后控件跳位")
    - 页 rect 和 --size 不一致
    - Time/Number 按 format 算的内容总宽超过 rect(会静默重叠或被裁)

  提示
    - 子控件 rect 明显超出父控件范围(被裁掉的部分不会显示)
    - 组合控件少了可选的百分比文字零件
    - 一页里的控件特别多(合成任务和每帧耗时都会涨，见 platform.md)
    - 背景色还是控件库默认值(#8DEEDB / #D2EE45 / #D9EE94 这类 6 位色)
    - 背景色是 #ffffffff(设备端不填充，但编辑器预览画成白色，两边不一致)
    - 图片路径找不到
    - 图片带 alpha 却用 RGB565(透明变黑底)，或没 alpha 却用 ARGB8565(白占 50% 空间)
    - "假透明"：ARGB8565 的图整张 alpha 全 255(把底色画进图里了)
    - 透明区的 RGB 整片不是黑(把底色填进了透明区，真机上可能显示成一块色底)
    - 图片比控件 rect 大(框架不缩放，超出部分被裁掉)

本脚本用仓库里两个工程标定过：SmallColorTFT 和 BT_Watch 都是 0 错误，
所以它一旦报 ERROR，就是真的错。

## 设计原则：静默失败类的检查要"按程度报"，不要"按存在报"

这类检查的价值全在信噪比 —— 一旦刷屏，真问题就被淹没，人会开始整体忽略它。
本脚本三次栽在这上面，每次都是"按存在报"被实测数据否掉：

| 检查 | 按存在报 | 实测分布 | 改成 |
|---|---|---|---|
| 图片小于 rect | 359 条 | 图标居中摆在大框里是常态 | 只报"图比 rect 大"(真丢内容) |
| Time 内容超宽 | 误报官方工程 | 分隔符不足会截断，实际不超宽 | 先判截断，再比宽度 |
| 透明区 RGB 非黑 | 97 张里报 63 张 | 抗锯齿残留 ≤10.5%，整块底色 >50% | 占比 >50% 才报 |

**加新检查时先在两个样例工程上跑一遍看噪音量**，几十条起就说明判据需要
换成"按程度"：找一个能把"正常残留"和"真错"分开的阈值，并把实测分布写进注释。
"""
import sys
import os
import re
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jlui import (setup_stdout, load, iter_pages, page_nodes, typecode, ename_of,
                  css_of, css_groups_of, rect_of, color_format_of, prop_by_name, props,
                  iter_images, read_image_size, png_alpha_stats,
                  measure_digit_content,
                  TYPENAME, COMPOSITE_PARTS, CHILD_KEYS, RING_MAX_TASK)

ENAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
# 控件库模板自带的 6 位默认色。留着它等于给控件加了一块不透明底色，
# 而工具里看着像"没设过"——两个工程里这些值零散分布，多半是没人管的残留。
LIB_DEFAULT_COLORS = {'#8deedb', '#d2ee45', '#d9ee94', '#368fee', '#eed9c1'}


class Report:
    def __init__(self):
        self.err = []
        self.warn = []

    def error(self, where, msg):
        self.err.append((where, msg))

    def note(self, where, msg):
        self.warn.append((where, msg))

    def dump(self):
        for w, m in self.err:
            print('ERROR  %-34s %s' % (w, m))
        for w, m in self.warn:
            print('note   %-34s %s' % (w, m))
        print('\n%d 个错误, %d 个提示' % (len(self.err), len(self.warn)))
        return 1 if self.err else 0


def node_label(node, pi):
    return 'p%d/%s' % (pi, node.get('-name') or node.get('caption') or '?')


# 溢出几个像素是工具里排版的常态(文字控件尤其多)，只报明显越界的
OVERFLOW_TOLERANCE = 4
# 单页可见控件数的提醒门槛。不是硬上限：实测本仓库 SmallColorTFT 的
# 系统页有 87 个默认可见控件，设备上工作正常，所以定得比它高一截。
BUSY_PAGE = 120
# 小于这个面积的图不报"没 alpha 却用 ARGB8565"：几十个像素省下来的那点空间
# 不值得为它改格式，报了只是噪音（实例：进度条的 2x8 实心游标块）。
TINY_IMAGE = 200
# 透明像素里"RGB 非黑"的占比超过这个值才报。少量非黑是抗锯齿边缘的正常残留
# (实测一批 LANCZOS 缩放出来的图集，最高 10.5%)；整块底色填进透明区会接近 100%。
BAD_ALPHA_RATIO = 0.5


def check_rect_in_parent(r, pr, tol=OVERFLOW_TOLERANCE):
    """r 是否落在父的 (0,0,pw,ph) 内 —— 坐标相对父节点，不是绝对坐标。"""
    if not r or not pr:
        return True
    return (r['x'] >= -tol and r['y'] >= -tol
            and r['x'] + r['width'] <= pr['width'] + tol
            and r['y'] + r['height'] <= pr['height'] + tol)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--size', help='屏幕尺寸，如 240x240；不给就以第一页的 rect 为准')
    args = ap.parse_args()

    doc = load(args.project)
    root = os.path.dirname(os.path.abspath(args.project))
    rp = Report()

    want = None
    if args.size:
        w, h = args.size.lower().split('x')
        want = {'width': int(w), 'height': int(h)}

    enames = collections.defaultdict(list)
    white_bg = []

    for pi, page in iter_pages(doc):
        # --- 页节点的 rect 必须是只有 "rect" 一个键的裸对象
        praw = None
        for p in props(page):
            if 'rect' in p:
                praw = p
                break
        if praw is None:
            rp.error('page %d' % pi, '页节点没有 rect')
        elif set(praw.keys()) != {'rect'}:
            rp.error('page %d' % pi,
                     '页 rect 多带了键 %s；工具读页尺寸时要求它是裸对象，'
                     '否则整页控件几何全变 0' % sorted(set(praw.keys()) - {'rect'}))

        prect = rect_of(page)
        if prect:
            if want is None:
                want = {'width': prect['width'], 'height': prect['height']}
            elif (prect['width'], prect['height']) != (want['width'], want['height']):
                rp.error('page %d' % pi, '页尺寸 %dx%d 和其它页/--size 的 %dx%d 不一致'
                         % (prect['width'], prect['height'], want['width'], want['height']))

        # --- 图层色彩格式
        for layer in page.get('layer', []) or []:
            cf = color_format_of(layer)
            if cf != 'OSD16':
                rp.error(node_label(layer, pi),
                         '图层 color_format = %s，彩屏必须是 OSD16'
                         '(OSD1 是单色点阵屏的路径，见 jl-dot-ui)' % cf)

        nodes = page_nodes(page)
        visible_ctrl = 0

        for node, _depth, parent in nodes:
            where = node_label(node, pi)
            tc = typecode(node)
            if tc is None:
                rp.error(where, '认不出控件类型：caption=%r, -type=%r 都不在类型码表里，'
                                '生成器会给它类型码 0' % (node.get('caption'), node.get('-type')))

            idp = prop_by_name(node, 'id')
            if idp is None:
                rp.error(where, 'property 里没有 id 项，控件拿不到 ID')
            else:
                e = ename_of(node)
                if not e:
                    rp.error(where, 'id 项里 ename 为空')
                else:
                    if not ENAME_RE.match(e):
                        rp.error(where, 'ename %r 含非法字符，只能用 [A-Za-z0-9_] 且不能数字开头' % e)
                    enames[e.upper()].append(where)

            # --- 几何
            r = rect_of(node)
            if r is None:
                rp.error(where, '没有 rect')
            else:
                if r['width'] <= 0 or r['height'] <= 0:
                    rp.error(where, 'rect 尺寸为 %dx%d，这个控件永远画不出来'
                             % (r['width'], r['height']))
                pr = rect_of(parent) if parent is not None else None
                # 列表条目本来就排在列表可视区之外，靠滚动露出来，不算越界
                in_list = parent is not None and typecode(parent) == 5
                if pr and not in_list and not check_rect_in_parent(r, pr):
                    rp.note(where, 'rect (%d,%d %dx%d) 超出父节点 %dx%d，超出部分会被裁掉'
                            % (r['x'], r['y'], r['width'], r['height'],
                               pr['width'], pr['height']))

            css = css_of(node)
            inv = css.get('invisible', {})
            is_hidden = str(inv.get('value', inv.get('default'))).lower() == 'true'
            if tc is not None and tc not in (3, 4) and not is_hidden:
                visible_ctrl += 1

            # --- 多份 element_css：第二份是高亮态，框架选中时整份换掉
            #
            # Time 控件支持两份 css。time_onchange 收到 highlight 事件(event 8)时
            # 直接 ui_core_set_element_css() 换成第二份 —— rect 也在里面。所以两份
            # 唯一该有的差异是 background_color(常态透明 / 高亮填一块底色)，
            # 其余字段不一致就是漏改，表现为"选中之后控件整个跳到别的位置"。
            #
            # 噪音量：本仓库两个工程一共只有 8 个控件带两份 css(时钟设置 6 个 +
            # 闹钟设置 2 个)，修完为 0 条，所以这条按"存在即报"是安全的。
            groups = css_groups_of(node)
            if len(groups) > 1:
                for gi in range(1, len(groups)):
                    diff = []
                    for key in groups[0]:
                        if key == 'background_color':
                            continue        # 这一项本来就该不一样
                        a, b = groups[0].get(key), groups[gi].get(key)
                        if a != b:
                            diff.append(key)
                    if diff:
                        detail = ''
                        if 'rect' in diff:
                            r0 = groups[0]['rect'].get('rect') or {}
                            r1 = (groups[gi].get('rect') or {}).get('rect') or {}
                            detail = ('；普通 %d,%d %dx%d 高亮 %d,%d %dx%d'
                                      % (r0.get('x', 0), r0.get('y', 0),
                                         r0.get('width', 0), r0.get('height', 0),
                                         r1.get('x', 0), r1.get('y', 0),
                                         r1.get('width', 0), r1.get('height', 0)))
                        rp.error(where,
                                 'css[%d](高亮态)和 css[0](普通态)差在 %s —— 选中时框架会整份'
                                 '换成高亮那份，这些字段必须一致%s'
                                 % (gi, '/'.join(diff), detail))

            # --- 背景色
            bc = css.get('background_color', {})
            col = (bc.get('background-color') or '').strip().lower()
            if col in LIB_DEFAULT_COLORS:
                rp.note(where, '背景色 %s 是控件库默认值；设了颜色就会被 fill 成一块不透明色，'
                               '想透明请留空串' % col)
            elif col == '#ffffffff':
                # 设备端把它当"不填充"，但 ui-tools 编辑器会画成不透明白 ——
                # 两边不一致。样例工程里大量存在，是最容易被照抄的坑。
                white_bg.append(where)

            # --- 图片：存在性 / alpha 和 image-type 是否配套 / 尺寸和 rect 是否匹配
            for pitem, rel, itype in iter_images(node):
                full = os.path.join(root, rel.replace('\\', '/'))
                if not os.path.exists(full):
                    rp.note(where, '图片找不到: %s' % rel)
                    continue
                info = read_image_size(full)
                if not info:
                    continue
                iw, ih, has_alpha = info
                name = os.path.basename(rel)

                # 框架不会因为格式不对而报错，透明就是悄悄变成黑底
                if has_alpha and itype == 'RGB565':
                    rp.note(where, '%s 带 alpha 通道但 image-type=RGB565，'
                                   '透明区会被填成不透明色；要透明请用 ARGB8565' % name)
                elif (not has_alpha) and itype == 'ARGB8565' and iw * ih >= TINY_IMAGE:
                    rp.note(where, '%s（%dx%d）源图没有 alpha 通道却用 ARGB8565，'
                                   '白白多占 50%% 资源；不需要透明就用 RGB565'
                            % (name, iw, ih))
                elif has_alpha and itype == 'ARGB8565' and iw * ih >= TINY_IMAGE:
                    st = png_alpha_stats(full)
                    if st and st['all_opaque']:
                        # "假透明"：带 alpha 通道但整张全不透明，多半把底色画进去了。
                        # 摆在同色页面上和真透明像素级一致，换底色才露馅。
                        rp.note(where, '%s（%dx%d）有 alpha 通道但整张 alpha 全是 255，'
                                       '像是把底色画进图里了；换底色/加底图时会露出方块'
                                % (name, iw, ih))
                    elif (st and st['transparent']
                          and st['bad_transparent'] > st['transparent'] * BAD_ALPHA_RATIO):
                        # 透明像素的 RGB 应当是 0。整片非黑 = 把底色填进了透明区，
                        # 真机上可能显示成一块色底。
                        # 少量非黑是抗锯齿边缘的正常残留(实测 <11%)，所以要按比例判。
                        rp.note(where, '%s（%dx%d）有 %d/%d 个全透明像素的 RGB 不是黑，'
                                       '像是把底色填进了透明区；真机上可能显示成一块色底'
                                % (name, iw, ih, st['bad_transparent'], st['transparent']))

                # number/delimiter 是"一位一张图"，控件 rect 是整串的宽度，没法直接比
                if pitem.get('-name') in ('number', 'delimiter'):
                    continue
                # 只报"图比 rect 大"：框架不缩放，多出来的部分直接被裁掉，是真丢内容。
                # 反过来"图比 rect 小"在真实工程里是常态(图标居中摆在更大的框里)，
                # 报出来只会淹没真问题 —— 实测样例工程会刷出 300+ 条。
                if r and r['width'] > 0 and r['height'] > 0:
                    if iw > r['width'] or ih > r['height']:
                        rp.note(where, '%s 是 %dx%d，比控件 rect 的 %dx%d 大，'
                                       '框架不缩放，超出部分被裁掉'
                                % (name, iw, ih, r['width'], r['height']))

            # --- Time/Number：按 format 算内容总宽，和 rect 比
            # 改了数字图尺寸却忘了放大控件 rect 是高频错误，后果是静默重叠或被裁
            if tc in (10, 15) and r and r['width'] > 0:
                got = measure_digit_content(node, root, 'time' if tc == 10 else 'number')
                if got:
                    content_w, detail, truncated, exact = got
                    if truncated:
                        rp.note(where, 'format 里的分隔符比 delimiter 列表多，'
                                       '显示会从用完那里截断，后面的字段不显示（%s）' % detail)
                    elif content_w > r['width'] and exact:
                        rp.error(where, '按 format 算内容宽 %d > rect 宽 %d，会被裁掉或和'
                                        '旁边的控件重叠（%s）'
                                 % (content_w, r['width'], detail))
                    elif content_w > r['width']:
                        # 数字图不等宽、或 format 里有不带宽度的 %d，只能给上界
                        rp.note(where, '内容宽上界 %d > rect 宽 %d，可能被裁或重叠'
                                       '（数字图不等宽或用了 %%d，只能估上界）（%s）'
                                % (content_w, r['width'], detail))
                    elif content_w > r['width'] - 2:
                        rp.note(where, '内容宽 %d 和 rect 宽 %d 只差 %d px，'
                                       '再改字号/图宽就溢出了（%s）'
                                % (content_w, r['width'], r['width'] - content_w, detail))

            # --- 组合控件零件
            cap = node.get('caption')
            if cap in COMPOSITE_PARTS:
                kids = []
                for k in CHILD_KEYS:
                    kids += [c.get('caption') for c in (node.get(k) or []) if isinstance(c, dict)]
                for part in COMPOSITE_PARTS[cap]:
                    if part in kids:
                        continue
                    # 百分比文字是可选零件，工程里常常不放
                    if part.endswith('_text'):
                        rp.note(where, '组合控件 %s 没有 %r 零件(可选，不显示百分比就不用放)'
                                % (cap, part))
                    else:
                        rp.error(where, '组合控件 %s 缺零件 caption=%r；'
                                        'caption 决定类型码，改名后它会退化成普通控件且不报错'
                                 % (cap, part))

        if visible_ctrl > BUSY_PAGE:
            rp.note('page %d' % pi,
                    '这一页有 %d 个默认可见的控件，比仓库里现有最满的一页(87 个)还多；'
                    '每个控件至少一个 IMB 合成任务，注意帧率和内存' % visible_ctrl)

    if white_bg:
        rp.note('background_color',
                '有 %d 个控件的背景色是 #ffffffff：设备端等同"不填充"，但 ui-tools '
                '编辑器会画成不透明白，预览和实机对不上。要透明请改成空串 ""。'
                '例: %s' % (len(white_bg), ', '.join(white_bg[:4])))

    for e, wheres in enames.items():
        if len(wheres) > 1:
            rp.error(e, 'ename 重复了 %d 次: %s；ID 会撞车，应用代码只能操作到其中一个'
                     % (len(wheres), ', '.join(wheres[:4])))

    print('工程 %s' % args.project)
    print('屏幕 %dx%d, %d 页\n' % (want['width'], want['height'],
                                   len(doc.get('pages', []))) if want else '')
    return rp.dump()


if __name__ == '__main__':
    sys.exit(main())
