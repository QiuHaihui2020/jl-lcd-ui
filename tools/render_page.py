# -*- coding: utf-8 -*-
"""从工程 json 渲染一页，用来代替"手敲坐标画效果图"做排版自检。

    python render_page.py <工程.json> <页号> -o out.png
    python render_page.py <工程.json> 3 -o out.png --sample CLOCK_TIME_HMS=15 \
                          --sample CLOCK_WEEK_PIC=5 --sample CLOCK_TEMP_BAR=48

⚠ 这个脚本需要 pillow（`pip install pillow`）。tools/ 里其它三个脚本是零依赖的，
只有它不是 —— 因为它本质上就是在做图像合成，自己解码 PNG 再做 alpha 合成不值当。

## 为什么值得用它，而不是自己按坐标画一张效果图

它复刻了设备端的几条绘制规则，所以能**同时**照出配色错、坐标错、裁切和遮挡：

- **背景填充**：`(color & 0xFFFFFF) != 0xFFFFFF` 才填一块不透明色。
  自己画效果图时几乎不会实现这条，于是照不出"某个控件的背景色把整屏刷白"
  这类问题 —— 坐标明明是对的，画面却全白。
- **绘制顺序**：先填背景色 → 画背景图 → 画自己的内容 → 按 `layout[]` 顺序递归子节点，
  **靠后的盖在上面**（和设备端一致，所以能照出遮挡）。
- **align**：Time/Number 的内容先算总宽，再按 LEFT/CENTER/RIGHT 定起始 x。
  不实现这条就看不出"数值没有右对齐紧贴单位"这类问题。
- **slider**：`left_pic` 按百分比 **crop**（不是缩放），顺序 right→left→slider_pic，
  画完不再递归子节点。
- **Battery**：图在 `image` 属性里，**不是** `normal_image`（漏了这条电池位置会一直空着）。

## 已知不支持（看到这些"没画出来"是正常的，不是渲染错了）

| 不支持 | 说明 |
|---|---|
| Text 控件的文字 | 走字库/strpic，这里只用虚框标出位置和尺寸 |
| `highlight_image` | 只画 `normal_image` |
| GRID/列表的滚动和高亮 | 条目按各自 rect 静态画 |
| JPEG 背景图 | pillow 能读，但设备端是硬件解码，效果可能有差异 |
| `play_mode` 轮播 | 只画第 0 帧 |
| slider 的 `follow_pic` | 未实现（工程里没人用），滑块位置按 `本体宽 × 百分比` 放 |

**它是排版自检工具，不是模拟器。** 要看真实效果还是得上板。
"""
import json
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jlui import (setup_stdout, load as load_project, css_of, rect_of, ename_of,
                  prop_by_name, expand_time_format, expand_number_format)

try:
    from PIL import Image, ImageDraw
except ImportError:
    # 这条提示可能在还没设好编码的终端里出现，所以英文写完整、中文只作补充
    setup_stdout()
    sys.stderr.write(
        'render_page.py needs pillow. Install it with:\n'
        '    pip install pillow\n'
        'It is the only script here with a dependency; the other three need none.\n'
        '(此脚本需要 pillow，其余三个脚本零依赖)\n')
    sys.exit(2)

# 没被任何东西填到的地方显示成深灰，好和"真的画了一块黑"区分开
EMPTY_BG = (40, 40, 40, 255)
TEXT_BOX = (150, 110, 200, 90)      # Text 控件的占位框


def fill_color(value):
    """空串 / #ffffffff 都是不填充；其余按 24 位 RGB 填一块不透明色。

    这条判定和设备端一致（见 SKILL.md 铁律 4），是这个渲染器的价值所在。
    """
    if not value:
        return None
    v = value.strip().lstrip('#')
    if len(v) == 8:                 # #AARRGGBB：砍掉 alpha 再比
        v = v[2:]
    if len(v) != 6:
        return None
    try:
        rgb = int(v, 16)
    except ValueError:
        return None
    if rgb == 0xFFFFFF:
        return None
    return ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF, 255)


class Renderer:
    def __init__(self, root, samples):
        self.root = root
        self.samples = samples          # {ENAME: 字符串或整数}
        self.missing = []               # 找不到的图，最后一起报

    def img(self, rel):
        if not rel:
            return None
        path = os.path.join(self.root, rel.replace('\\', '/'))
        if not os.path.exists(path):
            self.missing.append(rel)
            return None
        try:
            return Image.open(path).convert('RGBA')
        except Exception:
            self.missing.append(rel)
            return None

    def sample_text(self, node, en, kind):
        """Time/Number 要显示的示例串。没指定就按 format 自动生成。

        数字位填 8（笔画最满，最容易看出溢出），分隔符位填 '/'。

        ⚠ 不带宽度的 `%d` 这里只填 **1 位**，不是 check_project.py 用的
        u16 上界 5 位 —— 那个上界是给"会不会溢出"的静态判断用的；
        渲染要的是**典型值**，填 5 个 8 会画出一片假的溢出，反而误导。
        真要看最坏情况，显式 `--sample ENAME=88888`。
        """
        got = self.samples.get(en)
        if isinstance(got, str):
            return got
        fmt_p = prop_by_name(node, 'format')
        fmt = (fmt_p.get('default') if fmt_p else '') or ''
        items = (expand_time_format(fmt) if kind == 'time'
                 else expand_number_format(fmt))
        out = []
        for k, n in items:
            if k == 'd':
                out.append('8' * n)
            elif k == 'd*':
                out.append('8')          # %d：典型值 1 位
            else:
                out.append('/')
        return ''.join(out) or '8'

    def draw_digits(self, node, canvas, x, y, w, kind):
        digits_p = prop_by_name(node, 'number')
        delim_p = prop_by_name(node, 'delimiter')
        digits = (digits_p.get('list') if digits_p else None) or []
        delim = (delim_p.get('list') if delim_p else None) or []
        if not digits:
            return
        text = self.sample_text(node, ename_of(node), kind)

        def glyph(ch, sep_i):
            if ch.isdigit() and int(ch) < len(digits):
                return self.img(digits[int(ch)])
            if sep_i < len(delim):
                return self.img(delim[sep_i])
            return None

        # 先量总宽，align 要用
        total, sep_i = 0, 0
        for ch in text:
            im = glyph(ch, sep_i)
            if not ch.isdigit():
                sep_i += 1
            total += im.width if im else 0

        css = css_of(node)
        al = (css.get('align', {}) or {}).get('default', 'ALIGN_CENTER')
        if al == 'ALIGN_RIGHT':
            cx = x + w - total
        elif al == 'ALIGN_LEFT':
            cx = x
        else:
            cx = x + (w - total) // 2

        sep_i = 0
        for ch in text:
            im = glyph(ch, sep_i)
            if not ch.isdigit():
                sep_i += 1
            if im:
                canvas.alpha_composite(im, (cx, y))
                cx += im.width

    def draw_slider(self, node, canvas, x, y, w):
        parts = {ch.get('caption'): ch for ch in (node.get('layout') or [])}
        pct = self.samples.get(ename_of(node), 50)
        try:
            pct = int(pct)
        except (TypeError, ValueError):
            pct = 50
        for key in ('right_pic', 'left_pic', 'slider_pic'):
            part = parts.get(key)
            if part is None:
                continue
            pr = rect_of(part)
            pc = css_of(part)
            im = self.img((pc.get('background_image', {}) or {}).get('background-image'))
            if not im or not pr:
                continue
            if key == 'left_pic':
                # 按百分比裁，不是缩放 —— 和设备端一致
                im = im.crop((0, 0, max(1, im.width * pct // 100), im.height))
                canvas.alpha_composite(im, (x + pr['x'], y + pr['y']))
            elif key == 'slider_pic':
                # 宽度基准是 slider 本体(见 project.md)；未实现 follow_pic
                canvas.alpha_composite(im, (x + w * pct // 100, y + pr['y']))
            else:
                canvas.alpha_composite(im, (x + pr['x'], y + pr['y']))

    def draw(self, node, canvas, ox, oy):
        css = css_of(node)
        inv = css.get('invisible', {}) or {}
        if str(inv.get('value', inv.get('default'))).lower() == 'true':
            return
        r = rect_of(node)
        if not r:
            return
        x, y, w, h = ox + r['x'], oy + r['y'], r['width'], r['height']

        col = fill_color((css.get('background_color', {}) or {}).get('background-color'))
        if col:
            ImageDraw.Draw(canvas).rectangle((x, y, x + w - 1, y + h - 1), fill=col)

        bi = (css.get('background_image', {}) or {}).get('background-image')
        if bi:
            im = self.img(bi)
            if im:
                canvas.alpha_composite(
                    im.crop((0, 0, min(w, im.width), min(h, im.height))), (x, y))

        cap = node.get('caption')
        en = ename_of(node)

        if cap in ('图片', '电池电量'):
            key = 'normal_image' if cap == '图片' else 'image'   # Battery 用 image！
            p = prop_by_name(node, key)
            lst = (p.get('list') if p else None) or []
            idx = self.samples.get(en, 0)
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                idx = 0
            if lst and 0 <= idx < len(lst):
                im = self.img(lst[idx])
                if im:
                    canvas.alpha_composite(im, (x, y))

        elif cap in ('时间', '数字'):
            self.draw_digits(node, canvas, x, y, w, 'time' if cap == '时间' else 'number')

        elif cap == '文字':
            # 走字库/strpic，这里画不了，用虚框标出位置和尺寸
            ImageDraw.Draw(canvas, 'RGBA').rectangle(
                (x, y, x + w - 1, y + h - 1), outline=TEXT_BOX)

        elif cap in ('slider', 'vslider'):
            self.draw_slider(node, canvas, x, y, w)
            return                      # 零件已经自己画完了

        for child in (node.get('layout') or []) + (node.get('listwidget') or []):
            self.draw(child, canvas, x, y)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('page', type=int)
    ap.add_argument('-o', '--out', default='render.png')
    ap.add_argument('--zoom', type=int, default=2, help='放大倍数，默认 2')
    ap.add_argument('--sample', action='append', default=[], metavar='ENAME=值',
                    help='指定某控件显示什么：Time/Number 给串("15")，'
                         'ImageList/Battery 给第几张(整数)，slider 给百分比')
    args = ap.parse_args()

    samples = {}
    for item in args.sample:
        if '=' in item:
            k, v = item.split('=', 1)
            samples[k.strip()] = v.strip()

    doc = load_project(args.project)
    pages = doc.get('pages') or []
    if not 0 <= args.page < len(pages):
        print('页号超范围：工程只有 %d 页' % len(pages))
        return 1
    page = pages[args.page]
    pr = rect_of(page)

    rd = Renderer(os.path.dirname(os.path.abspath(args.project)), samples)
    canvas = Image.new('RGBA', (pr['width'], pr['height']), EMPTY_BG)
    for layer in page.get('layer') or []:
        rd.draw(layer, canvas, 0, 0)

    z = max(1, args.zoom)
    canvas.convert('RGB').resize((pr['width'] * z, pr['height'] * z),
                                 Image.NEAREST).save(args.out)
    print('渲染完成 -> %s  (%dx%d, 放大 %dx)'
          % (args.out, pr['width'], pr['height'], z))
    if rd.missing:
        print('⚠ %d 张图没找到，画面里对应位置是空的：' % len(rd.missing))
        for m in sorted(set(rd.missing))[:10]:
            print('   ', m)
    print('提示：深灰区域 = 没有任何控件填到；紫色虚框 = Text 控件占位（文字画不了）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
