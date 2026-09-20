# -*- coding: utf-8 -*-
"""
杰理彩屏 UI 工程(.json)的公共解析层：树遍历、类型码、控件 ID 计算。

被 gen_ename.py / check_project.py / dump_tree.py 共用。

ID 编码规则来自设备端 interface/ui/jl_ui/ui/control.h 的三个官方宏：
    ui_id2prj(id)  = (id >> 26) & 0x3f    工程号(UI 编译工具里设，本仓库两个工程都是 0)
    ui_id2page(id) = (id >> 17) & 0x1ff   页序号(在 pages[] 里的下标)
    ui_id2type(id) = (id >> 10) & 0x7f    控件类型码(CTRL_TYPE_*)
    低 10 位                               同页同类型内的序号，按页内遍历顺序从 0 递增

已用本仓库两个工程标定：SmallColorTFT(510 个控件) + BT_Watch(62 个)，
与工具生成的 ename.h 逐个比对 0 处不一致。
"""
import json
import sys
import os
import re
import struct
import collections

# ---------------------------------------------------------------- 类型码
# 键是 json 节点的 caption(优先) 或 -type，值是设备端 CTRL_TYPE_*。
# caption 优先是关键：slider/vslider 的零件 -type 全是 ImageList，
# 只有 caption 能把它们和普通图片区分开。
TYPECODE = {
    '页面': 2, 'page': 2, 'ScenesScreen': 2,
    '布局': 3, 'NewLayout': 3,
    '图层': 4, 'NewLayer': 4,
    '表格控件': 5, '垂直列表': 5, '水平列表': 5,
    'NewGrid': 5, 'VerticalList': 5, 'HorizontalList': 5,
    '按钮': 7, 'Button': 7,
    '图片': 8, 'ImageList': 8,
    '电池电量': 9, 'Battery': 9,
    '时间': 10, 'Time': 10,
    '文字': 12, 'Text': 12,
    '数字': 15, 'Number': 15, 'number': 15,
    'progressbar': 20, 'progressbar_highlight': 21,
    'multiprogressbar': 22, 'multiprogressbar_highlight': 23,
    'watch': 24, 'watch_hour': 25, 'watch_min': 26, 'watch_sec': 27,
    'slider': 28, 'right_pic': 29, 'left_pic': 30,
    'slider_pic': 31, 'slider_text': 32,
    'vslider': 33, 'vslider_right_pic': 34, 'vslider_left_pic': 35,
    'vslider_pic': 36, 'vslider_text': 37,
    'compass': 38, 'compass_bkimg': 39, 'compass_indicator': 40,
}

TYPENAME = {
    2: 'WINDOW', 3: 'LAYOUT', 4: 'LAYER', 5: 'GRID', 6: 'LIST', 7: 'BUTTON',
    8: 'PIC', 9: 'BATTERY', 10: 'TIME', 11: 'CAMERA', 12: 'TEXT',
    13: 'ANIMATION', 14: 'PLAYER', 15: 'NUMBER',
    20: 'PROGRESS', 21: 'PROGRESS_HL', 22: 'MULTIPROGRESS', 23: 'MULTIPROGRESS_HL',
    24: 'WATCH', 25: 'WATCH_HOUR', 26: 'WATCH_MIN', 27: 'WATCH_SEC',
    28: 'SLIDER', 29: 'SLIDER_UNSEL', 30: 'SLIDER_SEL', 31: 'SLIDER_PIC', 32: 'SLIDER_TEXT',
    33: 'VSLIDER', 34: 'VSLIDER_UNSEL', 35: 'VSLIDER_SEL', 36: 'VSLIDER_PIC', 37: 'VSLIDER_TEXT',
    38: 'COMPASS', 39: 'COMPASS_BK', 40: 'COMPASS_IND',
}

# 组合控件的零件 caption —— 改了就退化成普通控件，而且不报错
COMPOSITE_PARTS = {
    'slider': ['right_pic', 'left_pic', 'slider_pic', 'slider_text'],
    'vslider': ['vslider_right_pic', 'vslider_left_pic', 'vslider_pic', 'vslider_text'],
    'compass': ['compass_bkimg', 'compass_indicator'],
    'watch': ['watch_hour', 'watch_min', 'watch_sec'],
    'progressbar': ['progressbar_highlight'],
    'multiprogressbar': ['multiprogressbar_highlight'],
}

CHILD_KEYS = ('layout', 'listwidget', 'widget')

# 每个 imb_task_head(一个图层)缓存的硬件任务块数量，见 asm/imb.h 的 RING_MAX_TASK。
# 注意它不是"一页最多几个控件"：反编译 imb.c 的 imb_task_ring_kick() 可见，
# 前 40 个任务复用 root->task_tab[] 里缓存的任务块，第 41 个往后每帧
# imb_malloc(332) 重新分配。超了只是变慢/更碎，不是画不出来。
RING_MAX_TASK = 40


def read_image_size(path):
    """读 BMP/PNG/JPEG 的宽高，不依赖 PIL。读不出返回 None。

    还返回是否带 alpha 通道 —— image-type 选 RGB565 还是 ARGB8565 要看它。
    返回 (width, height, has_alpha) 或 None。
    """
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
            if head[:2] == b'BM':                       # BMP
                w, h = struct.unpack('<ii', head[18:26])
                bpp = struct.unpack('<H', head[28:30])[0]
                return (abs(w), abs(h), bpp == 32)
            if head[:8] == b'\x89PNG\r\n\x1a\n':         # PNG
                w, h = struct.unpack('>II', head[16:24])
                color_type = head[25]
                return (w, h, color_type in (4, 6))     # 4=灰+A, 6=RGBA
            if head[:2] == b'\xff\xd8':                 # JPEG：扫 SOF 段
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        return None
                    if b != b'\xff':
                        continue
                    marker = f.read(1)
                    if marker in (b'\xc0', b'\xc1', b'\xc2'):
                        f.read(3)
                        h, w = struct.unpack('>HH', f.read(4))
                        return (w, h, False)
                    seg = f.read(2)
                    if len(seg) < 2:
                        return None
                    f.seek(struct.unpack('>H', seg)[0] - 2, 1)
    except Exception:
        return None
    return None


def expand_time_format(fmt):
    """Time 的 format 展开成 [('d', 位数) | ('sep', None), ...]。

    规则见 reference/project.md（反编译 time_vsprintf 得到）：
    Y=4位 M/D/h/m/s=2位，其它字符都是分隔符，按出现顺序取 delimiter。
    """
    widths = {'Y': 4, 'M': 2, 'D': 2, 'h': 2, 'm': 2, 's': 2}
    out = []
    for ch in fmt or '':
        if ch in widths:
            out.append(('d', widths[ch]))
        else:
            out.append(('sep', None))
    return out


def expand_number_format(fmt):
    """Number 的 format 展开。只认 %d / %Nd / %0Nd，其它字符是分隔符。

    不带宽度的 %d 实际显示几位要看运行时的值，静态算不出来。但控件内部是
    u16(见 widgets.md)，最大 65535 = 5 位，所以按 5 位算是个安全的上界。
    返回的第二个值标记结果是精确还是上界。
    """
    out = []
    i = 0
    s = fmt or ''
    while i < len(s):
        if s[i] == '%':
            j = i + 1
            if j < len(s) and s[j] == '0':
                j += 1
            digits = ''
            while j < len(s) and s[j].isdigit():
                digits += s[j]
                j += 1
            if j < len(s) and s[j] == 'd':
                if digits:
                    out.append(('d', int(digits)))
                else:
                    out.append(('d*', 5))      # %d：按 u16 上界 5 位算
                i = j + 1
                continue
        out.append(('sep', None))
        i += 1
    return out


def measure_digit_content(node, root, fmt_kind):
    """按 format 算 Time/Number 的内容总宽，和 rect 比对用。

    返回 (内容宽, 说明串, 是否截断, 是否精确) 或 None（图读不到时不猜）。

    框架侧是逐张图累加宽度（`ui_platform.c` 的 get_strpic_width()：
    `width += file.width`），**没有字间距也没有 kerning**。所以：
    - 10 张数字图等宽时，这里算出来是**精确值**
    - 不等宽、或 format 里有不带宽度的 %d 时，只能给**上界**
    """
    fmt_p = prop_by_name(node, 'format')
    num_p = prop_by_name(node, 'number')
    dlm_p = prop_by_name(node, 'delimiter')
    if not fmt_p or not num_p or not (num_p.get('list') or []):
        return None
    fmt = fmt_p.get('default') or ''

    def widths_of(p):
        out = []
        for rel in (p.get('list') or []):
            info = read_image_size(os.path.join(root, rel.replace('\\', '/')))
            if not info:
                return None
            out.append(info[0])
        return out

    nw = widths_of(num_p)
    if not nw:
        return None
    dw = widths_of(dlm_p) if dlm_p else []
    digit_w = max(nw)
    exact = (min(nw) == max(nw))       # 数字图等宽才算得准

    items = (expand_time_format(fmt) if fmt_kind == 'time'
             else expand_number_format(fmt))
    total = 0
    sep_i = 0          # 已经用掉几张分隔符图
    parts = []
    truncated = False
    for kind, n in items:
        if kind in ('d', 'd*'):
            total += digit_w * n
            parts.append('%d位x%d%s' % (n, digit_w, '(上界)' if kind == 'd*' else ''))
            if kind == 'd*':
                exact = False
            continue
        # 分隔符：按出现顺序取 delimiter[sep_i]
        if sep_i < len(dw):
            total += dw[sep_i]
            parts.append('分隔%d' % dw[sep_i])
            sep_i += 1
        elif fmt_kind == 'time':
            # Time：分隔符列表用完(读到 0xFFFF)就从这里截断，后面根本不画。
            # 不这么处理会把"分隔符配少了"的工程误报成"内容超宽"。
            parts.append('[分隔符只有 %d 张，从这里截断]' % len(dw))
            truncated = True
            break
        elif dw:
            # Number：用完之后固定复用 delimiter[0]，不截断
            total += dw[0]
            parts.append('分隔%d' % dw[0])
    return total, '%s = %s' % (fmt, ' + '.join(parts)), truncated, exact


def png_alpha_is_all_opaque(path):
    """PNG 的 alpha 是不是全 255。薄封装，细节见 png_alpha_stats()。"""
    st = png_alpha_stats(path)
    return None if st is None else st['all_opaque']


def png_alpha_stats(path):
    """解 PNG 的 alpha 通道，查两类"透明没做对"的问题。

    返回 {'all_opaque': bool, 'bad_transparent': int, 'transparent': int}，
    判断不了返回 None。两类问题机理不同，都只在真机上露馅：

    1. **假透明**(all_opaque)：alpha 全 255，等于把底色画进了图里。
       摆在同色页面上和真透明**像素级一致**，自己渲染效果图完全看不出来，
       换个底色/加底图才露馅。

    2. **透明区 RGB 不是黑**(bad_transparent)：alpha 对，但全透明像素的 RGB
       填了图标色/白色。实测官方切图的透明区 RGB 全是 0；填了别的颜色时，
       真机上可能显示成一大块色底。典型来源是
       `Image.new('RGBA', size, color + (0,))` 再 putalpha —— 透明区 RGB
       被填成了 color。

    只处理最常见的 8bit RGBA/GA。
    """
    try:
        import zlib
        with open(path, 'rb') as f:
            if f.read(8) != b'\x89PNG\r\n\x1a\n':
                return None
            w = h = depth = ctype = None
            idat = b''
            while True:
                head = f.read(8)
                if len(head) < 8:
                    break
                ln, typ = struct.unpack('>I', head[:4])[0], head[4:8]
                data = f.read(ln)
                f.read(4)                                   # CRC
                if typ == b'IHDR':
                    w, h, depth, ctype = struct.unpack('>IIBB', data[:10])
                    if depth != 8 or ctype not in (4, 6):
                        return None                         # 只处理 8bit RGBA/GA
                elif typ == b'IDAT':
                    idat += data
                elif typ == b'IEND':
                    break
            if not idat or not w:
                return None
            raw = zlib.decompress(idat)
            nch = 4 if ctype == 6 else 2                    # RGBA / 灰+A
            all_opaque, transparent, bad_transparent = True, 0, 0
            stride = w * nch
            prev = bytearray(stride)
            pos = 0
            for _y in range(h):
                ft = raw[pos]
                pos += 1
                line = bytearray(raw[pos:pos + stride])
                pos += stride
                # PNG 的 5 种行过滤，必须还原才能读到真实 alpha
                for i in range(stride):
                    a = line[i - nch] if i >= nch else 0
                    b = prev[i]
                    c = prev[i - nch] if i >= nch else 0
                    if ft == 1:
                        line[i] = (line[i] + a) & 0xFF
                    elif ft == 2:
                        line[i] = (line[i] + b) & 0xFF
                    elif ft == 3:
                        line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
                    elif ft == 4:
                        p = a + b - c
                        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                        pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                        line[i] = (line[i] + pr) & 0xFF
                for i in range(nch - 1, stride, nch):
                    a = line[i]
                    if a != 255:
                        all_opaque = False
                    if a == 0:
                        transparent += 1
                        # 全透明像素的 RGB 应当是 0；不是就是把底色画进图里了
                        if nch == 4:
                            if line[i - 3] or line[i - 2] or line[i - 1]:
                                bad_transparent += 1
                        elif line[i - 1]:
                            bad_transparent += 1
                prev = line
            return {'all_opaque': all_opaque,
                    'bad_transparent': bad_transparent,
                    'transparent': transparent}
    except Exception:
        return None


def iter_images(node):
    """yield (属性项, 图片相对路径, image-type)，覆盖背景图和各种图片列表。"""
    css = css_of(node)
    bi = css.get('background_image')
    if bi and (bi.get('background-image') or '').strip():
        yield bi, bi['background-image'].strip(), bi.get('image-type')
    for p in props(node):
        if p.get('-type') in ('piclist', 'arrlist'):
            for item in p.get('list', []) or []:
                if item and item.strip():
                    yield p, item.strip(), p.get('image-type')


def setup_stdout():
    """Windows 控制台默认 GBK，工程里全是中文节点名，不切就是一堆 UnicodeEncodeError。"""
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def typecode(node):
    """caption 优先，退回 -type；都认不出返回 None(生成器会把它当类型码 0)。"""
    c = node.get('caption')
    if c in TYPECODE:
        return TYPECODE[c]
    t = node.get('-type')
    if t in TYPECODE:
        return TYPECODE[t]
    return None


def props(node):
    return node.get('property', []) or []


def prop_by_name(node, name):
    for p in props(node):
        if p.get('-name') == name:
            return p
    return None


def ename_of(node):
    p = prop_by_name(node, 'id')
    return p.get('ename') if p else None


def css_of(node):
    """element_css 的 7 项拍平成 {name: 属性项}。属性项里值放哪个键取决于 -type。"""
    p = prop_by_name(node, 'element_css')
    if not p:
        return {}
    try:
        return {q.get('-name'): q for q in p['struct'][0]}
    except (KeyError, IndexError, TypeError):
        return {}


def css_groups_of(node):
    """element_css 的【每一份】，按出现顺序返回 [{name: 属性项}, ...]。

    绝大多数控件只有一份。Time 可以有两份：css[0] 普通态、css[1] 高亮态，
    选中时框架整份换掉(见 widgets.md 的"Time 的双 css")。css_of() 只看
    第一份，要比对高亮态必须用这个。
    """
    p = prop_by_name(node, 'element_css')
    if not p:
        return []
    out = []
    for grp in p.get('struct', []) or []:
        try:
            out.append({q.get('-name'): q for q in grp})
        except (AttributeError, TypeError):
            pass
    return out


def rect_of(node):
    """控件的 rect 在 element_css 里；页节点的 rect 是 property[0] 下的裸对象。"""
    c = css_of(node)
    if 'rect' in c:
        return c['rect'].get('rect')
    for p in props(node):
        if set(p.keys()) == {'rect'}:
            return p['rect']
    return None


def color_format_of(layer):
    """图层的色彩格式。json 里通常只有 default 一项(没被显式改过)，那就是生效值。"""
    p = prop_by_name(layer, 'color_format')
    if not p:
        return None
    for k in ('value', 'select', 'current', 'default'):
        if k in p:
            return p[k]
    return None


def walk(node, out, depth=0, parent=None):
    """页内遍历：先自己，再按 layout/listwidget/widget 的数组顺序递归。

    这个顺序就是 ID 低 10 位序号的分配顺序，也是设备端的绘制顺序
    (靠后的画在上面)，不要改成别的遍历方式。
    """
    out.append((node, depth, parent))
    for k in CHILD_KEYS:
        for c in node.get(k, []) or []:
            if isinstance(c, dict):
                walk(c, out, depth + 1, node)
    return out


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def iter_pages(doc):
    """yield (page_index, page_node)"""
    for i, p in enumerate(doc.get('pages', []) or []):
        yield i, p


def page_nodes(page):
    """一页里全部节点(不含页自身)，按遍历顺序。返回 [(node, depth, parent), ...]"""
    out = []
    for layer in page.get('layer', []) or []:
        walk(layer, out, 0, page)
    return out


def make_id(prj, page_index, type_code, seq):
    return (prj << 26) | (page_index << 17) | (type_code << 10) | seq


def build_ids(doc, prj=0):
    """整个工程的 {ENAME: id}，含 PAGE_n。ename 统一转大写(工具就是这么生成宏名的)。"""
    ids = {}
    for pi, page in iter_pages(doc):
        ids['PAGE_%d' % pi] = make_id(prj, pi, TYPECODE['页面'], pi)
        cnt = collections.Counter()
        for node, _depth, _parent in page_nodes(page):
            tc = typecode(node)
            if tc is None:
                continue
            seq = cnt[tc]
            cnt[tc] += 1
            e = ename_of(node)
            if e:
                ids[e.upper()] = make_id(prj, pi, tc, seq)
    return ids


def parse_ename_h(path):
    """读 ename.h / style_JL_new.h，返回 {宏名: 值}。"""
    out = {}
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = re.match(r'#define\s+(\w+)\s+0[xX]([0-9A-Fa-f]+)', line.strip())
            if m:
                out[m.group(1)] = int(m.group(2), 16)
    return out


def find_project_json(d):
    """工程目录下找 .json 工程文件(排除工具自己的配置)。"""
    skip = {'ResBuilder.xml'}
    cands = []
    for name in os.listdir(d):
        if name.lower().endswith('.json') and name not in skip:
            p = os.path.join(d, name)
            try:
                with open(p, encoding='utf-8') as f:
                    head = f.read(200)
                if '"-type": "project"' in head or '"pages"' in head:
                    cands.append(p)
            except Exception:
                pass
    return cands
