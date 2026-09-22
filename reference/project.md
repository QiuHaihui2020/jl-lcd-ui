# 工程脚本（.json）怎么写

工程文件就是 UTF-8 的 JSON（`SmallColorTFT.json` 10MB、`BT_Watch.json` 1MB，
体积主要来自每个节点都带一整套控件库模板字段）。

看结构不要 grep，用 `tools/dump_tree.py <工程.json> -p <页号>`（加 `-v` 看
format/align/image-type）。

---

## 0. ⚠ 程序化读写工程文件的固定模板

这几 MB 的 json 只能用脚本改。**回写时四个参数缺一不可**：

```python
import json

with open(PRJ, encoding='utf-8') as f:
    prj = json.load(f)

...改 prj...

with open(PRJ, 'w', encoding='utf-8', newline='\n') as f:   # newline='\n' 是关键
    json.dump(prj, f, ensure_ascii=False, indent=4, sort_keys=True)
```

| 参数 | 不写会怎样 |
|---|---|
| `newline='\n'` | Windows 上按文本模式写 = **CRLF**，而工具写出来的是 LF。<br>结果整个文件逐行变化，只改一页也会得到<br>`153359 insertions(+), 148133 deletions(-)` 这种 diff |
| `encoding='utf-8'` | 中文节点名写成 GBK，工具读不了 |
| `ensure_ascii=False` | 中文变 `\uXXXX` 转义，整个文件面目全非 |
| `indent=4` | 缩进对不上，同样全文件 diff |
| `sort_keys=True` | 键顺序对不上，同样全文件 diff |

> `sort_keys=True` 是证实过的，不是碰运气：拿 `object_pairs_hook` 逐对象验过
> 两个样例工程共 **33322 个 JSON 对象，非字典序 0 个**。工具自己写出来就是排序的。

### ⚠ 还差一步：空容器要展开成两行，否则纯回写就有 5000 行 diff

上面五个参数齐了**也不是逐字节还原**。工具把空数组/空对象写成两行，
`json.dump` 写成一行：

```
工具：  "widget": [                json.dump：  "widget": [],
        ],
```

拿 `SmallColorTFT.json` 什么都不改地跑一遍 load→dump，实测
**168804 行变成 167451 行，diff 5414 行**。功能上没影响（工具照样读得进去），
但你自己改的那几行会被淹掉，review 时看不出改了什么。

回写时加一步还原：

```python
import re

PAT = re.compile(r'(?m)^(\s*)("(?:[^"\\]|\\.)*": )(\[\]|\{\})(,?)$')

def expand(m):
    ind, key, pair, tail = m.group(1), m.group(2), m.group(3), m.group(4)
    return '%s%s%s\n%s%s%s' % (ind, key, pair[0], ind, pair[1], tail)

txt = json.dumps(prj, ensure_ascii=False, indent=4, sort_keys=True)
txt = PAT.sub(expand, txt)
with open(PRJ, 'w', encoding='utf-8', newline='\n') as f:
    f.write(txt)
```

加上这步之后，往一页里加 20 个控件的实测 diff 是
**7143 增 / 86 删** —— 增量全是新节点（每个节点带一整套控件库模板字段，
约 355 行），删改行数就是你实际动的属性数。

改完 `git diff --stat` 应当只有你动的那几行加上新节点的体积。
**如果删除行数上千，先别继续**，一定是上面某个参数或这步还原漏了。

> ⚠ 用 Bash 的 heredoc 跑这段会失败：heredoc 会吃掉反斜杠，
> `[^"\\]` 变成 `[^"\]`，正则直接报 `unterminated character set`。
> **把脚本写成文件再 `python 文件.py`**，别内联进 heredoc。

---

## 0.5 ⚠⚠ 改 json 之前先确认 GUI 已经关了

**`ui-tools.exe` 保存时，是拿它"打开那一刻的内存副本"整份覆盖文件的。**
所以 AI 和人同时动一个工程时会出现这种事：

```
13:35  人打开 ui-tools（内存里是此刻的 json）
13:38  AI 改 json 写盘（65 处背景色改成空串）
13:41  人在 GUI 里点保存 → 整个文件被 13:35 的副本覆盖
       → AI 的改动连同页名、布局背景色一起消失
```

现象非常迷惑：**改动"自己消失了"**，而且 `git diff` 干净得像没改过。
这不是工具在做格式规范化（`BT_Watch` 里 11 处空串好端端留着，
说明工具会保留空串），纯粹是 stale buffer 覆盖。

两条规矩：

- **AI 动 json 前，确认 ui-tools 已关闭**（改之前问一句，或看有没有 `.lock`/临时文件）。
- **人在 GUI 里保存过之后，AI 必须重新读文件再改** —— 不要基于之前读到的内容继续改。

踩一次就是白干一轮。

### 配套做法：每次写盘后记一份属性快照

光"重读再改"不够 —— **重读之后你分不清哪些差异是人有意改的、哪些是误碰的**。

所以 AI 每次写盘后，把自己动过的关键属性记成一张表
（实战里是 22 个 rect + 4 个 format + 3 个 align + 动画参数）。
人在 GUI 里动过之后跑一次比对，两类差异立刻分得开。

这个做法在实战里当场查出：主布局底色被误改、3 个 rect 被动过，
其中一个把星期控件的高度从 20 改成 18 —— **会把图裁掉 2px**，
而这种改动在界面上几乎看不出来，不比对根本发现不了。

---

## 1. 树的形状

父子关系靠**不同的键名**表达，每一层的键名不一样，写错了工具读不到子节点：

```
project
└── pages[]        → page          （-class: ScenesScreen）
    └── layer[]    → NewLayer      图层，一页一个，整屏
        └── layout[]   → NewLayout 布局
            ├── layout[]  → 叶子控件 / 嵌套 NewLayout / 列表 / 组合控件
            └── VerticalList / HorizontalList / NewGrid
                └── listwidget[] → NewLayout（一个条目一个）
```

| 父 | 子数组的键 | 允许的子节点 |
|---|---|---|
| project | `pages` | page |
| page | `layer` | NewLayer |
| NewLayer | `layout` | NewLayout |
| NewLayout | `layout` | 叶子控件、NewLayout、列表、组合控件 |
| VerticalList / HorizontalList / NewGrid | `listwidget` | NewLayout |

叶子控件（Text / ImageList / Battery / Time / Number）不再有子节点。
每个节点还有一个 `widget: []`，两个工程里**全是空的**，照抄即可。

## 2. `-class` / `-type` / `caption` 各管什么

| 字段 | 管什么 | 取值 |
|---|---|---|
| `-class` | 结构角色 | `ScenesScreen` `NewLayer` `NewLayout` `NewList` `NewGrid` `NewFrame` |
| `-type` | 编辑器里的控件种类 | `page` `NewLayer` `NewLayout` `Text` `ImageList` `Battery` `Time` `Number` `VerticalList` `HorizontalList` `NewGrid` |
| `caption` | **决定类型码**，同时是编辑器里显示的名字 | 见下表 |
| `-name` | 编辑器里的节点名，可以是中文，**不影响生成，也不要求唯一** | `文字_12` / `BaseForm_393` |

> `-name` 不必唯一是实证过的：样例工程里 `-name` 就叫 `VerticalList` 的节点
> 分别有 22 个和 3 个，工程正常工作。造新节点时不用费劲编唯一名字 ——
> **要唯一的是 `ename`**，那才是代码的抓手。

`-class` 只有 6 个值，**它不是控件类型**；所有叶子控件的 `-class` 都是 `NewFrame`。
组合控件（slider 等）的 `-class` 是 `NewLayout`、`-type` 也是 `NewLayout`，
**只有 `caption` 说明它是 slider**。

### 类型码表（= 设备端 `control.h` 的 `CTRL_TYPE_*`）

| caption | 码 | | caption | 码 |
|---|---|---|---|---|
| 页面 | 2 | | slider | 28 |
| 布局 | 3 | | right_pic | 29 |
| 图层 | 4 | | left_pic | 30 |
| 垂直列表 / 水平列表 / 表格控件 | 5 | | slider_pic | 31 |
| 图片 | 8 | | slider_text | 32（可选零件） |
| 电池电量 | 9 | | vslider | 33 |
| 时间 | 10 | | vslider_right_pic / _left_pic / _pic / _text | 34/35/36/37 |
| 文字 | 12 | | compass | 38 |
| 数字 | 15 | | compass_bkimg / compass_indicator | 39/40 |
| progressbar / progressbar_highlight | 20/21 | | watch | 24 |
| multiprogressbar / _highlight | 22/23 | | watch_hour / _min / _sec | 25/26/27 |

查表规则是 **`caption` 优先，查不到才退回 `-type`**，都查不到就是类型码 0（画不出来）。
`tools/jlui.py` 里 `TYPECODE` 是同一张表。

## 3. 控件 ID 怎么来

```
id = (工程号 << 26) | (页下标 << 17) | (类型码 << 10) | 同页同类型内的序号
```

序号按**页内遍历顺序**（先自己、再按 `layout`/`listwidget` 数组顺序递归）从 0 递增。
`ename` 转大写后就是 `ename.h` 里的宏名。

```json
{"-name": "id", "-type": "id", "caption": "唯一ID号", "ename": "BT_MUSIC_NAME", "id": 0}
```

- `id` 那个键**永远是 0**，真正的 ID 是算出来的，不要去填它。
- `ename` 全工程唯一，只能 `[A-Za-z0-9_]` 且不能数字开头。
- 代码不碰的纯装饰控件可以留自动名（`BaseForm_393`），它一样占序号。

⚠ **在一页中间插控件会推移后面同类型控件的序号 → 它们的 ID 全变。**
插完必须跑：

```
python tools/gen_ename.py <工程.json> --check apps/soundbox/include/ui/style_JL_new.h
```

加在页末尾则不影响已有 ID。

### ⚠ 从别的页复制控件过来：名字会骗人，ID 不会

在 ui-tools 里把一整块（比如进度条、一排律动柱）从 A 页复制到 B 页时，
工具给新控件起的是**顺序自动名**，而且常常沿用原页的前缀词。
于是 B 页上会出现 `MUSIC_25` 这种名字 —— 它在**蓝牙页**，和音乐页的
`MUSIC_BAR` 是两个完全不同的控件：

```
MUSIC_BAR  0X87000   页 4(音乐页) 的 slider
MUSIC_25   0X27000   页 1(蓝牙页) 的 slider   ← 名字像音乐页的，其实不是
```

两件事必须做：

1. **代码里起业务别名**，别让正文出现看不出含义的自动名。
   页面私有的写在该页 action 文件顶部，跨页共用的写 `ui_style.h`：
   ```c
   /* 从音乐页复制过来的进度条，工具自动起名 MUSIC_25(0X27000，页1第0个 slider) */
   #define BT_MUSIC_BAR    MUSIC_25
   ```
   `REGISTER_UI_EVENT_HANDLER(BT_MUSIC_BAR)` 能正常工作 —— 那个宏是双层展开
   （`__REGISTER_UI_EVENT_HANDLER`），别名会先展开成数值再拼接符号名。

2. **绝不跨页共用 ID 常量数组**。ID 里带页下标，同一排 16 根柱子在两个页上
   是两套完全不同的值，各页各存一份：
   ```c
   static const int s_bt_spec_id[]    = { BT_SPEC_0,    ... };   /* 页 1 */
   static const int s_music_spec_id[] = { MUSIC_SPEC_00, ... };  /* 页 4 */
   ```
   共用一份的话是"能编译、能跑、就是刷不到任何控件"——
   刷进去的 ID 在本页不存在，只会打 `element is null`（见 `app.md`，
   那条警告的含义是"这次调用被吞了"）。

## 4. 坐标

- 单位像素，**相对父节点**，不是绝对坐标。
- 屏幕尺寸 = **页节点的 rect**。本仓库两个工程都是 240×240。
- 页节点的 rect 是个**裸对象**，`property` 里只有 `rect` 一个键，不能带 `-name`：

```json
"property": [ { "rect": {"x": 0, "y": 0, "width": 240, "height": 240} } ]
```

  带了 `-name` 工具就读不到页尺寸，**那一页所有控件的几何全变 0**，而且不报错。
- 控件的 rect 在 `element_css` 里。

列表条目的 rect 允许排到列表可视区之外（靠滚动露出来），
`check_project.py` 对 grid 的子节点不查越界。

## 5. `element_css` —— 每个控件都有的 7 项

顺序固定：`align` `invisible` `flags` `rect` `background_color` `background_image` `border`。
（图层还多一项 `z_order`，见下。）

```json
{"-name": "element_css", "-type": "struct", "caption": "CSS元素", "info": "",
 "struct": [[
   {"-name": "align",      "-type": "enum", "default": "ALIGN_CENTER",
    "enum": [{"ALIGN_LEFT":0},{"ALIGN_CENTER":1},{"ALIGN_RIGHT":2}]},
   {"-name": "invisible",  "-type": "enum", "default": "false",
    "enum": [{"true":1},{"false":0}]},
   {"-name": "flags",      "-type": "enum", "default": "ELM_FLAG_NORMAL", "enum": [...]},
   {"-name": "rect",       "-type": "rect", "rect": {"x":0,"y":0,"width":240,"height":30}},
   {"-name": "background_color", "-type": "background-color", "background-color": "#ffffffff"},
   {"-name": "background_image", "-type": "background-image", "background-image": "",
    "image-type": "ARGB8565"},
   {"-name": "border",     "-type": "border", "border": {"left":0,"top":0,"right":0,"bottom":0},
    "gray-color": 0}
 ]]}
```

⚠ **枚举类属性的当前值放在 `default` 里**，没有单独的 `value` 键。
所以「默认隐藏」就是把 `invisible` 的 `default` 改成 `"true"`：

```json
{"-name": "invisible", "-type": "enum", "caption": "默认隐藏", "default": "true",
 "enum": [{"true": 1}, {"false": 0}]}
```

`invisible: true` 的控件不显示，而且**整棵子树不参与按键分发** —— 弹层就是这么做的。

### background_color

见 SKILL.md 铁律 4。一句话：**要透明就写空串**。

`#ffffffff` 在设备端也是不填充，但**编辑器预览会画成不透明白** —— 两边不一致。
样例工程里 443 个控件写的是 `#ffffffff`，**别照抄**。
其它任何颜色（含控件库默认的 `#8DEEDB` 这类 6 位色）都会填一整块不透明色盖住下面。

### background_image / image-type

`background-image` 是相对工程目录的路径（`config/pic_lcd/xxx.bmp`）。
`image-type` 是打包成资源时的像素格式，工程里出现过的值：

| image-type | 用在哪 |
|---|---|
| `RGB565` | 不透明图，最省（2 字节/像素）。源文件通常是 24bpp BMP |
| `ARGB8565` | 需要透明的图（3 字节/像素）。**源文件必须是带 alpha 的 RGBA PNG** |
| `JPEG` | 大图/整屏背景，省 flash，解码由硬件做 |
| 空串 | 没设，由工具按图自己定 |

设备端支持的全部格式见 `asm/imb.h` 的 `enum LAYER_FORMAT`；
选哪个的完整依据（以及"假透明"这个坑）见 `platform.md` 第 4 节。

### 图层的 z_order

只有图层节点带 `z_order`，两个工程里都是 0。
设备端 `z_order == 0` 会被当成 31（最上层），实际工程里大家都一样，
于是**层次完全由 `layout[]` 数组顺序决定：靠后的画在上面**。

⚠ 和按键分发方向相反：画是从头到尾，按键是**从尾往前**。
所以弹层放在主布局后面，既画在上面、又先收到按键。

## 6. 各控件的专有属性

照抄控件库（`UITools/control/control.json`，组合控件在 `control/ex/*.json`）建节点，
只改下面这几项。

### 文字 Text

```json
{"-name":"source","-type":"text-str","caption":"数据源","default":"none","maxlength":8}
{"-name":"code","-type":"text-str","caption":"编码格式","default":"strpic","maxlength":8}
{"-name":"color","-type":"color","caption":"文字颜色","color":"#ff000000"}
{"-name":"color","-type":"color","caption":"高亮颜色","color":"#ff000000"}
{"-name":"str","-type":"text-pic","caption":"文字列表","compress":true,
 "default":"m1","list":["m1","m2","m42","m6"],"maxlength":100}
```

⚠ **两项 `-name` 都叫 `color`**，靠 `caption`（文字颜色 / 高亮颜色）和**出现顺序**区分。
读写时按顺序来，别去重、别合并。

`str.list` 里放的是**多国语言表的条目 id**（`m1` `m30` …），不是字面文字。
真正的文字在 `UITools/多国语言_128_64.xls` 里，运行时用
`ui_text_show_index_by_id(id, index)` 切换显示第几条。
运行时才知道的内容（歌名、设备名）用 `ui_text_set_text_by_id()`，不进这个列表。

### 图片 ImageList

```json
{"-name":"highlight","-type":"int8","caption":"默认高亮","default":0}
{"-name":"cent_x","-type":"int16","caption":"旋转中心点: X","default":0}
{"-name":"cent_y","-type":"int16","caption":"旋转中心点: Y","default":0}
{"-name":"play_mode","-type":"enum","caption":"播放设置","default":"PLAY_NONE",
 "enum":[{"PLAY_NONE":0},{"PLAY_ONCE":1},{"PLAY_LOOP":2}]}
{"-name":"interval","-type":"int16","caption":"播放间隔(ms)","default":100}
{"-name":"normal_image","-type":"piclist","caption":"图片列表","image-type":"RGB565",
 "list":["config/pic_lcd/V0.bmp","config/pic_lcd/V1.bmp"],"maxlength":30}
{"-name":"highlight_image","-type":"piclist","caption":"高亮图片列表","image-type":"","list":[]}
```

图标状态机（蓝牙已连/未连、播放/暂停）就是在 `normal_image.list` 里摆好几张，
运行时 `ui_pic_show_image_by_id(id, index)` 切。
`play_mode` 不为 `PLAY_NONE` 时它自己按 `interval` 轮播，做动画不用写代码。

### 数字 Number / 时间 Time

两者都是**用图片拼数字**，不走字库：

```json
{"-name":"format","-type":"text-str","caption":"格式","default":"m:s","maxlength":16}
{"-name":"number","-type":"arrlist","caption":"数字图片列表","image-type":"RGB565",
 "list":["config/pic_lcd/NUM0.BMP", ... 10 张 ...],"maxlength":10}
{"-name":"delimiter","-type":"arrlist","caption":"分隔符图片列表","image-type":"RGB565",
 "list":["config/pic_lcd/NUMT.bmp"],"maxlength":10}
{"-name":"auto_cnt","-type":"enum","caption":"自动记时","default":"NO",
 "enum":[{"YES":1},{"NO":0}]}
```

`number.list` 必须正好 10 张（0-9），顺序就是数值。
播放进度这种「分:秒」也用 Time 控件。

⚠ Time 的「文字颜色」那项 `-type` 是 `background-color`（不是 `color`），
是工具的历史遗留，照抄别改。

### Time 的 `format` 语法（反编译 `ui_time.c` 的 `time_vsprintf()` 确认）

**区分大小写**，这是最容易错的地方：

| 字符 | 取什么 | 输出 |
|---|---|---|
| `Y` | 年 | 4 位，补零 |
| `M` | **月** | 2 位，补零 |
| `D` | **日** | 2 位，补零 |
| `h` | 时 | 2 位，补零 |
| `m` | **分** | 2 位，补零 |
| `s` | 秒 | 2 位，补零 |
| 其它任何字符 | —— | 原样输出，当分隔符 |

所以：

- **日期是 `Y-M-D` 或 `M-D`，不是 `y-m-d` / `m-d`** ——
  小写 `m` 是分钟，小写 `y`/`d` 根本不是字段，会被当成分隔符原样输出。
  这个错误在工具里看不出来，上板才发现日期位置显示的是分钟。
- **单字段完全合法**：只写 `h` 就只显示小时（两位）。
  需要时分秒分三个控件不同字号时就这么做。
- **一律补零**，没有"不补零"的写法。

### ⚠ 分隔符是按出现顺序取图，不是按字符查表

展开成字符串后逐字符映射成图片索引：

```c
for (i = 0, j = 0; i < len; i++) {
    if ('0' <= str[i] && str[i] <= '9')  idx = info->number[str[i] - '0'];
    else                                 idx = info->delimiter[j++];   /* ← 按顺序取下一项 */
    if (idx == -1) { 到这里截断，后面不显示; }
    buf[i] = idx;
}
```

两个后果：

- **分隔符字符写什么都一样**。`h:m:s` 和 `h-m-s` 显示完全相同 ——
  决定画什么的是 `delimiter.list` 里的第几张图，不是 `:` 这个字符。
- **有几个分隔符就要列几项**。`h:m:s` 有两个 `:`，`delimiter.list` 要有 2 项
  （同一张冒号图列两次）。只列 1 项的话，走到第二个冒号读到 -1，
  **从那里截断，秒就不显示了**。

另外：`number.list` 为空（或首项是 0/-1）时，整串**不走图片，直接交给 ASCII 字库**
渲染。所以"用图片拼数字"和"用字库画数字"是靠有没有配 `number.list` 切换的。

### Number 的 `format`

printf 的一个子集，只认 `%d` / `%Nd` / `%0Nd`（N 是 1~8）。
不支持的格式设备端会打印 `the format %s not support yet!`。
样例工程里出现过的：`%d` `%02d` `%04d` `%02d/%02d` `%03d.%01d`。

⚠ **宽度是取模截断，不是撑宽**：值先算 `value % 10^宽度` 再 sprintf，
所以 `%02d` 传 123 显示的是 `23`。位数不够不会自动变宽。

⚠ **显示不了负数**：那步取模是**无符号**的（`urem`），而 `unumber.number[]`
是 `u32`，传 -4 会变成 `4294967292 % 100 = 92`。
要显示负号见 `widgets.md` 的 Number 段。

`numbs = 2` 时两个值按 `format` 里两个 `%d` 的位置排，中间的字符
（`%02d/%02d` 里那个 `/`）同样走 `delimiter.list` 按顺序取图。

### 电池 Battery

```json
{"-name":"image","-type":"piclist","caption":"电量图片列表","image-type":"RGB565",
 "list":["BATTLVL1.BMP","BATTLVL2.BMP","BATTLVL3.BMP","BATTLVL4.BMP","BATTLVL5.BMP"]}
{"-name":"charge_image","-type":"piclist","caption":"充电图片列表","image-type":"","list":[]}
```

`ui_battery_set_level_by_id(id, percent, incharge)` 按百分比在 `image.list` 里挑一张；
`incharge` 非 0 时用 `charge_image`。

### 列表 VerticalList / HorizontalList

列表节点在**顶层**多几个键（不在 property 里）：

```json
{"-class":"NewList","-type":"VerticalList","caption":"垂直列表",
 "orientation":"Vertical",   /* 或 "Horizontal" */
 "sizehw": 16,               /* 条目在滚动方向上的尺寸(像素) */
 "space": 0,                 /* 条目间距 */
 "listwidget":[ ...每个条目一个 NewLayout... ],
 "widget":[]}
```

property 里只有两项：

```json
{"-name":"scroll_mode","-type":"enum","caption":"滚动方式","default":"SCROLL",
 "enum":[{"SCROLL":0},{"PAGE":1}]}
{"-name":"highlight_index","-type":"int8","caption":"默认高亮行号","default":0}
```

条目自己的 rect 按 `sizehw` 依次排（`0,0` `0,16` `0,32` …），
可以排到列表 rect 之外，滚动时才露出来。

### 组合控件 slider

```
NewLayout  caption="slider"   ← 类型码 28，property: id / element_css / step / luascript
├ ImageList caption="right_pic"    未选中部分的图（29）
├ ImageList caption="left_pic"     已选中部分的图（30）
├ ImageList caption="slider_pic"   滑块（31）
└ ImageList caption="slider_text"  百分比文字（32，可选，工程里常不放）
```

**四个零件的 caption 一个字都不能改**，改了类型码就变，控件退化且不报错。
vslider 同理，caption 前缀换成 `vslider_`。

⚠ **零件的图片走 `element_css.background_image`，不是 `normal_image`。**
零件的 property 精简到只有 `id` + `element_css` 两项，**根本没有 `normal_image`
这一项**，别照普通 ImageList 的写法去找。一个零件长这样：

```json
{
  "-class": "NewFrame", "-name": "图片_301", "-type": "ImageList",
  "caption": "right_pic", "icon": "", "tip": "", "version": "1", "widget": [],
  "property": [
    {"-name": "id", "-type": "id", "caption": "ID号", "ename": "TEMP_BAR_BG", "id": 0},
    {"-name": "element_css", "-type": "struct", "caption": "CSS元素", "info": "",
     "struct": [[
       {"-name": "align", "-type": "enum", "default": "ALIGN_LEFT", "enum": [...]},
       {"-name": "invisible", "-type": "enum", "default": "false", "enum": [...]},
       {"-name": "flags", "-type": "enum", "default": "ELM_FLAG_NORMAL", "enum": [...]},
       {"-name": "rect", "-type": "rect", "rect": {"x":0,"y":0,"width":92,"height":8}},
       {"-name": "background_color", "-type": "background-color", "background-color": ""},
       {"-name": "background_image", "-type": "background-image",
        "background-image": "config/pic_clock/BAR_BG.png",   ← 图在这里
        "image-type": "ARGB8565"},
       {"-name": "border", "-type": "border", "border": {...}, "gray-color": 0}
     ]]}
  ]
}
```

### 零件 rect 的规矩

框架算填充宽度的实际逻辑（反编译 `slider_child_onchange()`）：

```c
ui_core_get_element_abs_rect(&slider->elm, &r);   /* r = slider 本体的 rect */
if (child_width > r.width)
    puts("SLIDER_CHILD_SELECTED_PIC is larger than SLIDER,Please check it!");
width  = (persent * r.width + 99) / 100;          /* ← 宽度基准是【本体】 */
r.left = <left_pic 自己的 rect>.left;              /* ← 起点是【零件】的左边 */
r.width = width;
get_rect_cover(draw_rect, &r, &c);                 /* 求交后裁剪 */
```

所以规矩是：

- **`right_pic` / `left_pic` 应当互相重合，并且与 slider 本体等宽、左对齐。**
  宽度基准取的是**本体**、起点取的是**零件**，两者不一致时百分比刻度就和槽对不上
  （50% 画出来不在槽的中间）。
- 零件比本体宽时，框架会 `puts` 一句
  `SLIDER_CHILD_SELECTED_PIC is larger than SLIDER,Please check it!` ——
  串口看到这句就是这里。窄了则不报，只是刻度不准。
- **`slider_pic` 是滑块本身的尺寸**，不是槽的尺寸；它的 x/y 是初始位置，
  运行时由框架按百分比挪。不要滑块就给个 `2×高` 的细条。
- ⚠ **slider 本体的高度必须 ≥ 滑块图的高度**，否则滑块超出本体的部分被裁掉，
  表现成"进度条下面缺一块"。滑块比轨道粗是常见设计，这时应该：
  **本体按滑块高来定，轨道图在本体里垂直居中**。

  ```
  ✗ 本体 122x4，滑块图 8x8         → 滑块上下各被裁 2px
  ✓ 本体 122x8，轨道 0,2 122x4，滑块 0,0 8x8
  ```

### ⚠ 一个"看着没问题、抄了才出问题"的反例

`SmallColorTFT` 页 2 的 `FM_SLIDER`：本体 `0,90 240×30`，而
`right_pic` / `left_pic` 都是 `15,0 210×11`（只有本体 87.5% 宽、还右移了 15）。

**但它在实机上没有任何可见问题**，因为那两个零件**都没配图，一个像素都不画**：

```
FM_SLIDER         SLIDER        0,90 240x30
├ FM_SLIDER_R     SLIDER_UNSEL  15,0 210x11     ← 无 background_image，不画
├ FM_SLIDER_L     SLIDER_SEL    15,0 210x11     ← 无 background_image，不画
└ FM_SLIDER_POINT SLIDER_PIC    112,0 19x15     img=DWNARROW.BMP   ← 指针
FM_SLIDER_PIC     PIC           0,15 240x15     img=FQBAR.BMP      ← 可见的槽(普通图片)
```

可见的频率槽是**旁边那个普通 ImageList**（`FQBAR.BMP`，`0,15 240×15`）。
指针行程按本体宽 240 算，可见槽也是 240 宽、x=0 起，两者对齐，所以没毛病。
（`FM_SLIDER_POINT` 初始 x=112，112+19/2 ≈ 121 ≈ 240/2 正好中点，
也印证了行程基准是**本体**。）

那个 `15,0 210×11` 是**没被用到的死数据** —— 大概当初摆了零件、后来改用旁边的
ImageList 画槽，零件 rect 就留在那儿了。它既不触发上面那句 `puts` 警告
（零件更小不是更大），也不产生错位。

**正因为它不会当场露馅，才是更危险的抄袭源**：照抄这组零件 rect 并**给它配上图**，
错位立刻显现，而且很难联想到是 rect 抄来的。要抄就抄页 3、页 4 那几个
严格等宽左对齐的。

另：`struct ui_slider` 里有个 `follow_pic` 运行时开关（**不在工程属性里**），
开了之后填充边缘按滑块中心算，适合"滑块骑在填充末端"的样式。

## 7. `action` —— 不写代码的联动

每个控件都有一项 `action`，声明「某事件发生时显示/隐藏某个对象」，
编进资源由框架执行：

```json
{"-name":"action","-type":"action","action":[
  {"-name":"event", "-type":"enum","default":"KEY_OK",
   "enum":[{"KEY_OK":13},{"KEY_MENU":15},{"TOUCH_CLICK":133},{"ON_CHANGE_INIT":151}, ...]},
  {"-name":"action","-type":"enum","default":"SHOW","enum":[{"SHOW":0},{"HIDE":1}]},
  {"-name":"object","-type":"...", ...}
]}
```

纯界面联动（按 MENU 弹出菜单层）用它就够，要跑业务逻辑还是得写回调。

## 8. `luascript`

每个控件都有一项 `luascript`。设备端有 Lua 虚拟机（`interface/ui/jl_ui/ui_vm/`，
开关是 `control.h` 里的 `ENABLE_LUA_VIRTUAL_MACHINE`），事件类型见
`enum luascript_event_type`。**两个工程都没用**，保持空着照抄即可。

## 9. 改完自查

1. 子数组键名对：`pages` / `layer` / `layout` / `listwidget`
2. `caption` 是控件库里的原值（决定类型码）
3. 页节点 rect 是裸对象、无 `-name`；所有页尺寸一致
4. `ename` 全工程唯一，只含 `[A-Za-z0-9_]`
5. rect 相对父节点、宽高不为 0
6. `property[]` 的项数和顺序照控件库来，重复的 `-name`（Text 的两个 `color`）不要合并
7. 引用的图片路径存在
8. `str.list` 里的 id 在多国语言表里有
9. 图层 `color_format` 是 `OSD16`

1-7、9 跑 `tools/check_project.py` 能兜住；ID 变化跑 `tools/gen_ename.py --check`。
**排版对不对最终只能靠 GUI 预览或上板看**，这套工具链没有出图的命令行。
