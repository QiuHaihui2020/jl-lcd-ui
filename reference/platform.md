# 彩屏在设备端是怎么画出来的

这一篇解释「为什么会这样」。排查「界面某块不对/闪/慢/花」的时候读它。

框架本体是 bitcode 库（`cpu/<芯片>/liba/ui_new.a`），但**平台层有源码**：
`cpu/<芯片>/ui_driver/interface/ui_platform.c`（4000+ 行）和
`cpu/<芯片>/ui_driver/lcd_drive/`。下面的结论都是从这两处 + 反编译库读出来的。

---

## 1. 和点阵屏根本不同的一点：没有 framebuffer

单色点阵屏是软件往一块 1bpp 显存里逐点写，写完整块推给屏。
**彩屏不是**。BR28 这一代的路径是：

```
控件绘制               每个控件 → 一个 IMB 任务（task）
   ↓
imb_task_head          一个图层一张任务表（链表 + task_tab[]）
   ↓
IMB 硬件               按任务表把图片/纯色/文字位图合成出若干行
   ↓
lcd_buffer_manager     几块行缓冲轮转（buffer_num，通常 2）
   ↓
IMD 硬件               把行缓冲推给 SPI/MCU/RGB 屏
```

框架调的 `platform_api->fill_rect` / `draw_image` / `show_text` 在
`ui_platform.c` 里**不是真的画像素**，而是
`imb_create_color()` / `imb_create_image()` / `imb_create_text()` ——
**往任务表里加一条任务**。真正的像素在 IMB 硬件里出。

这解释了彩屏上几个"反直觉"的现象：

- **控件数直接等于合成任务数**。一个控件哪怕只显示一个小图标，
  也占一条任务；设了背景色的控件额外再占一条纯色任务。
- **改一个控件不一定只重画那一块** —— 任务表变了就要重新合成，
  合成的粒度是"行块"（`buffer_size / (宽 × 2)` 行）。
- **透明是硬件混合**，不是"不写这些像素"（点阵屏那套 OR 叠加的心智模型在这里不成立）。

## 2. 图层 = 一张任务表 + 一份输出缓冲

`struct imb_task_head`（`asm/imb.h`）是图层在设备端的样子，几个关键字段：

```c
struct imb_task *task_tab[RING_MAX_TASK];   /* RING_MAX_TASK = 40 */
struct rect rect, canv, rect_ref, page_draw;
u8 *dispbuf;  u32 buflen;  u16 lines;  u8 bufnum;
u16 screen_width, screen_height, buf_stride;
int task_num;
u8 copy_to_psram, new_page, slider;  u16 effect_mode;  effect_cb effect_user;
```

### `RING_MAX_TASK = 40` 到底是什么

**不是"一页最多 40 个控件"，是任务块缓存的大小。**
反编译 `imb.c` 的 `imb_task_ring_kick()` 可见：遍历图层的任务链表，

- 前 40 个任务**复用** `root->task_tab[i]` 里缓存的硬件任务块
  （首次用时 `imb_malloc(332)`，之后一直留着）
- **第 41 个往后每一轮都 `imb_malloc(332)` 重新分配**

所以超过 40 的后果是**更慢、堆更碎，不是画不出来**
（实测样例工程系统页 87 个默认可见控件，设备上正常工作）。

任务是**绘制时**才创建的，由此可以推出这几条口径：

| 问题 | 答案 |
|---|---|
| 隐藏（`invisible=true`）的控件算不算？ | **不算**，整棵子树不绘制，不产生任务 |
| 同图层的多个弹层加在一起算吗？ | **不**，只算当前显示的那一套 |
| slider 算几个？ | **3 个**（三个零件各一张图）；父 `NewLayout` 不设背景色就是 0 |
| 设了 `background_color` 的控件？ | **额外多一条** SOLID 纯色任务 |

排版时的实际含义：**一屏同时可见的"有图/有色块的控件"控制在 40 以内**
就能全程走缓存；弹层因为不同时显示，不必计入。
- `copy_to_psram` / `effect_mode` / `slider` 那一组是给**页面滑动和转场特效**用的：
  有 PSRAM 时整页先合成到 PSRAM，再做特效。没有 PSRAM 就别开特效。

**所以"一页一个图层"不是风格建议，是省内存**：多一个图层就多一张任务表、
多一份输出缓冲。

## 3. 缓冲怎么分

屏驱动里那几个数字（以一个 240×240 SPI 屏为例）：

```c
#define LCD_BLOCK_W 240
#define LCD_BLOCK_H 40
#define BUF_NUM     2

struct imd_param param_t = {
    .scr_x = 0, .scr_y = 0, .scr_w = 240, .scr_h = 240,  /* 推屏区域 */
    .in_width = 240, .in_height = 240,                    /* IMB 的输出 = IMD 的输入 */
    .in_format = OUTPUT_FORMAT_RGB565,
    .lcd_width = 240, .lcd_height = 240,                  /* 屏物理尺寸 */
    .lcd_type = LCD_TYPE_SPI,
    .buffer_num  = BUF_NUM,
    .buffer_size = LCD_BLOCK_W * LCD_BLOCK_H * 2,         /* 一块 = 40 行 RGB565 */
    .fps = 60,
    .spi = { .spi_mode = ..., .port = SPI_PORTA, ... },
    .te_en = false,
};
```

- **不是整屏缓冲**，是 `BUF_NUM` 块 × `LCD_BLOCK_H` 行。
  240×40×2×2 = 38 KB，整屏双缓冲要 230 KB —— 片内 RAM 放不下。
- 合成按块进行，`draw_area()` 每合成一块就推一块。
- 有 PSRAM 时（`ENABLE_PSRAM_UI_FRAME`，跟着 `TCFG_PSRAM_DEV_ENABLE` 走）
  才会另外开整屏的 `psram_frame_buffer` / `psram_obuf`，用于特效和整帧操作。

调块高（`LCD_BLOCK_H`）是在 RAM 和推屏效率之间取舍：块太小推屏次数多，
块太大吃 RAM。改之前先算 `LCD_BLOCK_W × LCD_BLOCK_H × 2 × BUF_NUM`。

## 4. 图片格式：源文件格式和 image-type 必须配套

**这是彩屏上最容易做错、而且工具完全不报错的一处**：格式选错的结果是
"图标周围一圈黑底"，在编辑器预览里还看不出来。

IMB 支持的输入格式（`enum LAYER_FORMAT`）：
`ARGB8888` `RGB888` `RGB565` `L8` `AL88` `AL44` `A8` `L1` `ARGB8565` `OSD16` `SOLID` `JPEG`。
工具侧（工程 json 的 `image-type`）用的是三个，**每个都有对应的源文件格式**：

| image-type | 源文件通常是 | 每像素 | 什么时候用 |
|---|---|---|---|
| `RGB565` | 24bpp BMP，不压缩 | 2 B | 确定会铺满自己 rect 的不透明图：整屏底图、实心色块 |
| `ARGB8565` | **带 alpha 通道的 PNG（RGBA）** | 3 B | **任何要透明的图** —— 图标、非矩形的元素 |
| `JPEG` | jpg | 压缩 | 整屏照片类底图。硬件解码，省 flash，但解码要时间 |

样例工程里这个对应是 100% 干净的（`.bmp`→`RGB565` 591、`.png`→`ARGB8565` 181、
`.jpg`→`JPEG` 2，零交叉），但那是**惯例不是工具强制** —— 真正硬的只有下面这条方向：

- **24bpp BMP 本来就没有 alpha 通道，所以 `.bmp` 只能是 `RGB565`。**（这条是硬的）
- `.png` 打成 `RGB565` 大概率是允许的，只是**透明区会变成实色**。
- 没有 alpha 的源图打成 `ARGB8565` 也不报错，只是**白占 50% 空间**。

也就是说：**格式的选择依据是"这张图需不需要透明"，不是源文件后缀。**
`check_project.py` 查的正是这一层（alpha 通道和 `image-type` 配不配）。

### ⚠ 要透明就必须 RGBA PNG + ARGB8565，没有别的办法

常见的错误做法是**拿不透明图配一个"和底色一样的底"**。它只在底色永远不变时
看起来对，一旦：

- 给图层加了整屏底图
- 换了背景色
- 这个图标挪到别的背景上

就会露出一圈方块。**这是上板才看得出来的问题**，工具预览里是对的。

### 代价：ARGB8565 比 RGB565 多 50%，但**别按裸算估 flash**

`3 B/px` vs `2 B/px` 是**解码后在内存里**的大小。
存进 `JL.res` 时是**压缩**的，所以裸算只能当**上界**，真实占用往往小得多。

实测过一次：同一批 77 张图共 110248 像素，裸算 `ARGB8565` 约 322 KB，
而 `JL.res` 实际只涨了 **93789 字节 ≈ 92 KB**（压缩比约 3.5×）——
那批图六七成面积是全透明的，压得特别好。

所以正确的做法是**两步**：

1. **排版前**用裸算（像素总数 × 3 B）快速排除"明显放不下"的方案。
2. **导出后**量 `JL.res` 的增量，那才是真实占用（见 `export.md` 的导出后自检）。

⚠ 由此也可以直接劝退一个常见的错误取舍：**"为了省 flash 而退回 RGB565 做假透明"
基本不成立** —— 省下的那点空间在压缩后更少，而假透明是会在换底色时露馅的真 bug。

### AI 自己生成带 alpha 的图：缩放必须预乘 alpha

直接 `Image.resize()` 缩放 RGBA 图，**全透明像素的 RGB（通常是 0，即黑）
会被平均进边缘**，缩完一圈黑边。正确做法是先预乘、缩完再还原：

```python
import numpy as np
from PIL import Image

def down_rgba(im, w, h):
    """缩放带 alpha 的图。直接 resize 会在边缘渗出黑边。"""
    a = np.asarray(im.convert('RGBA'), dtype=np.float32)
    alpha = a[..., 3:4] / 255.0
    pre = np.concatenate([a[..., :3] * alpha, a[..., 3:4]], axis=-1)     # 预乘
    small = Image.fromarray(np.clip(pre, 0, 255).astype(np.uint8), 'RGBA') \
                 .resize((w, h), Image.LANCZOS)
    s = np.asarray(small, dtype=np.float32)
    sa = np.clip(s[..., 3:4], 1.0, 255.0) / 255.0                        # 还原
    return Image.fromarray(np.concatenate(
        [np.clip(s[..., :3] / sa, 0, 255), s[..., 3:4]], axis=-1).astype(np.uint8), 'RGBA')
```

### ⚠ 自检必须逐张贴棋盘格，不能只看拼好的整屏效果图

**这是真实翻车过的**：图做成了黑底不透明（假透明），而那一页恰好是纯黑底 ——
拼出来的整屏效果图和真透明**像素级一致**，自己怎么看都对，
换个底色/加张底图才露馅。

所以生成图集之后，**逐张贴到棋盘格背景上看**：

```python
from PIL import Image
import glob, os

CELL, PAD, COLS = 56, 8, 10

def checker(size, a=(200, 200, 200), b=(255, 255, 255), n=8):
    im = Image.new('RGB', (size, size), a)
    for y in range(0, size, n):
        for x in range(0, size, n):
            if (x // n + y // n) % 2:
                im.paste(b, (x, y, min(x + n, size), min(y + n, size)))
    return im

files = sorted(glob.glob('config/pic_clock/*.png'))
rows = (len(files) + COLS - 1) // COLS
sheet = Image.new('RGB', (COLS * (CELL + PAD) + PAD, rows * (CELL + PAD) + PAD), (60, 60, 60))
for i, f in enumerate(files):
    im = Image.open(f).convert('RGBA')
    im.thumbnail((CELL, CELL), Image.LANCZOS)
    cell = checker(CELL)
    cell.paste(im, ((CELL - im.width) // 2, (CELL - im.height) // 2), im)
    sheet.paste(cell, (PAD + (i % COLS) * (CELL + PAD), PAD + (i // COLS) * (CELL + PAD)))
sheet.save('contact_sheet.png')
```

棋盘格会让"假透明"一眼可见：真透明的图能看见格子，假透明的是一块实心方块。
`check_project.py` 也会把"ARGB8565 但整张 alpha 全 255"报出来，两个一起用。

### ⚠ 交付浅色素材时要主动说明

深色 UI 的素材（近白色的文字、图标）在看图软件里打开是
**白底上的白色内容 = 一片空白**，看起来像资源做坏了。
把这类图交给别人看之前先说一句，或者直接给上面那张棋盘格 contact sheet，
免得被误判成做错了。

### 其它选错的症状

| 现象 | 原因 |
|---|---|
| 图标周围一圈黑/白底 | 该用 `ARGB8565` 却用了 `RGB565`（或源图本来就没 alpha） |
| 资源包突然大了很多 | 不需要透明的图用了 `ARGB8565`（`check_project.py` 会提示） |
| 小图标用 `JPEG` 反而更慢 | 解码开销大于省下的读取，小图别用 JPEG |
| 图显示不全/被裁 | 图比控件 rect 大 —— **框架不缩放图片**，见下 |

### ⚠ 框架不缩放图片

图比 rect 大就被裁掉超出部分，小就按 `align` 摆在框里、四周留空。
两者都不报错。`check_project.py` 会把"图比 rect 大"报出来
（"小"不报，因为图标居中摆在大框里是常态）。

## 5. 背景色为什么"设了就盖住"

框架侧的判断（反编译 `ui_core.c` 得到）：

```c
if ((css.background_color & 0xFFFFFF) != 0xFFFFFF)
        platform_api->fill_rect(dc, css.background_color);
```

平台侧 `br28_fill_rect()` 走 `imb_create_color()` —— 建一条 **SOLID 纯色任务**，
它是不透明的，按任务顺序盖住下面已经合成的内容。

所以彩屏只有两态：**不填充（透明）/ 填一块不透明色**。
点阵屏那个"擦灭"的第三态在这里不存在。详见 SKILL.md 铁律 4。

### ⚠ 实测：传到 `br28_fill_rect()` 的不是 24 位裸色，别照着算"不填充"

在 BR28 + 240×240 ST7789 这版 SDK 上，给 `br28_fill_rect()` 加打印量到的实际值是：

```
[FILL] id=20c00 layer=0 color=64000841 prior=3 group=0 old=new
                              ^^^^ ^^^^
                              │    └─ 低 16 位 = RGB565。0x0841 正是 #080808
                              └────── 高半字 = 格式/alpha 位，不是颜色
```

也就是说 `background_color` 到这一层已经**不是 `#RRGGBB` 的 24 位值**了。
把它代回框架那个判据：

```
#ffffffff  →  0x6400FFFF  →  & 0xFFFFFF = 0x00FFFF  ≠ 0xFFFFFF  →  照样 fill
```

**推论：这版上 `#ffffffff` 不是"不填充"，而是填一块白。**
旁证是肉眼可见的：老蓝牙页和开机页都在 `0,60 240x120` 放了 `#ffffffff` 的布局，
屏上那一条就是**白的**。

> 这条和 SKILL.md 铁律 4 那张表的"设备端 `#ffffffff` = 不填充"**对不上**。
> 那张表是从 bitcode 的判据推的（推法本身没错），这里是在具体板子上量的。
> 差异出在"css 里存的到底是什么编码"，而那段转换在闭源的 `QtToolBin.exe` 里，
> 可能随 SDK 版本不同。
>
> **结论不变、而且更强：要透明就写空串。** 空串在两套说法下都是不填充，
> `#ffffffff` 则至少在这版上会给你一块白。
>
> 换一版 SDK 要自己确认时，`cpu/br28/ui_driver/interface/ui_platform.c` 里
> 留了现成的插装，把 `BR28_DEBUG_FILL_RECT` 改成 1 就能打出上面那行。

### 一个没查完的现象：整屏 SOLID 任务像是没被合成

同一次排查里还量到：`imb_task_dump()` 输出中，**整屏的 SOLID 纯色任务**
末尾那个标志是 `0`，而图片任务是 `1`；现象是页面切换后上一页的像素残留在
纯色背景该盖住的地方，但图片控件画得好好的。

当时验证过、可以排除的：`fill_rect` 确实被调用了且参数和正常页一致、
`get_rect_cover` 没走失败分支、没有残留图层（`root:1 task_num=0`）、
`RING_MAX_TASK` 没溢出。**根因没定位到**，后来重排版面后现象消失。

记在这里是为了下次遇到"背景色没生效但图片正常"时，不用再把上面这些重量一遍;
可考虑的绕法是**给页面铺一张整屏背景图**（纯色图 RLE 压完在 `JL.res` 里很小），
用图片任务替掉纯色任务。

`element_css` 里其实还有 `alpha:8`（和 `background_color:24` 同一个 u32），
以及 `css_rotate` / `css_ratio` —— 但**工具没把它们暴露成工程属性**，
两个样例工程里都没有可以填的地方。想要半透明，走图片的 `ARGB8565`。

## 6. 文字是怎么出来的：两套独立的机制

**固定文案和运行时字符串走的是完全不同的两条路**，连字体配置都不是同一个地方。
搞混了就会出现"改了字号没反应""界面上加不了这个字"这类问题。

| | 固定文案 | 运行时字符串 |
|---|---|---|
| 控件 `code` | `strpic` | `text` / `ascii` |
| 文字来源 | `多国语言_*.xls` | 代码传进来的 buf |
| 变成像素的时机 | **资源生成时离线渲染**成 1bpp 位图 | 设备端实时渲染 |
| 存在哪 | `JL.str` | —— |
| 字体/字号在哪配 | **`多国语言_*.xls` 里那个单元格自己的字体和字号** | `F_ASCII.PIX` / `F_UNIC.PIX` |
| 那份字体资源谁生成 | ResBuilder（step2） | `LCD_UI工程/字库工具/FontTool.exe` + `font.xml` |
| 怎么进固件 | 跟着 `JL.str` 走 | 烧录脚本单独 `packres … -o font` |

工程顶层的 `text_type: "1bpp"` / `texttype_type: "image"` 说的就是第一条路。

### ⚠⚠ strpic 的字号在 xls 单元格里，**不在** `ResBuilder.xml` 的 `<Fonts>`

这条踩过一次，而且**改错地方之后一切现象都像改对了**，极难自己发现：
工具预览会按新字号重画，但生成出来的 `JL.str` 一个字节都没变。

`ResBuilder.xml` 里那 22 个 `<fontNN lfHeight="-16"/>` 看着就是字号配置，
改它**完全不起作用**。实测记录：

| 证据 | 结果 |
|---|---|
| xls 里 m1「蓝牙」的单元格是**宋体 12 号** | `JL.str` 里 m1 的位图正好 **24×12**（两个字，每字 12×12） |
| xls 全表字号 12 / 8 / (Times New Roman)12 | `JL.str` 的 height 分布 **12×180 / 8×27 / 15×3** |
| 把 `<Fonts>` 全改成 `-24` 重跑 step2 | `JL.str` 的 `git diff` **空的**，一个字节没变 |
| 把 **xls 单元格**字号改成 24 重跑 | `JL.str` 16027→51991 字节，height 变 **24/27**，实机生效 |

所以**要改固定文案的字号，就去开 xls 全选改字号**，别碰 `<Fonts>`。

⚠ 同一行不同语言列可以是不同字体。上面 height=27 那几条就是因为那格用的是
**Times New Roman**，西文字体在同样字号下行高比宋体大 3px —— 行高按 24 排会被裁掉。

> `<Fonts>` 到底管什么没查出来。已知的是：它不参与 strpic 渲染，
> 而且 `<Fonts>` 有 22 个条目、`LanguageList` 正好也是 22 种语言。
> 在结论出来之前，**别把它当字号开关用**。

两个推论：

- **工程 `config/` 下的 `m*.png` 是离线渲染的中间产物**，
  json 里一处都没引用，别当成可以摆进界面的图片。
  而且它**不一定跟着 step2 更新**（实测跑完 step2 后这批 png 还是一个月前的），
  所以**不能拿它的尺寸判断当前字号** —— 要判断就去解析 `JL.str`（见 `export.md`）。

### 运行时文字的合成

`imb_create_text()` 把字库渲染出来的位图当成一条 **L1/L8 任务**交给 IMB，
颜色由任务的 `text_color` 给。几个约束：

- 任务的宽会被**对齐到 32 的倍数**（`(width + 31) / 32 * 32`），
  所以文字控件的 rect 宽最好也按这个规划，否则右边会有一小段浪费。
- 滚动（`FONT_SHOW_SCROLL`）是靠任务的 `scroll` / `scroll_offset` 做的，
  每帧改偏移 —— **滚动的文字会让这一页一直在重新合成**，费电。
  常驻页面上别放多条滚动文字。
- 滚动间隔是**全局**的（`text_set_strpic_scroll_interval()` 默认 250ms、
  `text_set_font_scroll_interval()` 默认 1000ms），不是每个控件各自设。

## 7. 资源从哪读

```c
/* ui_platform.c */
res_fopen(RES_PATH"JL/JL.sty", "r");
ui_core_set_style("JL.sty");
```

`JL.sty`(布局) / `JL.res`(图片) / `JL.str`(字符串图片) 三个文件被打成一个
res 分区，运行时通过 `res_fopen()` 按路径读。IMB 任务可以**直接从 flash 取图**
（`cur_in_flash` / `data_src = DATA_SRC_FLASH`），不用先整张读进 RAM ——
这是彩屏能用很多大图的前提。

资源放内置 flash 还是外挂 flash 由 `TCFG_UI_RES_MEDIUM` 决定，见 `export.md`。

### ⚠⚠ 每次 `ui_pic_show_image_by_id()` 都要重读一遍资源文件

**要按拍刷控件（律动条、动画、进度条）之前必须先知道这条，否则设计一开始就是错的。**

反编译 `ui_new.a` / `res_new.a` 的调用链：

```
ui_pic_show_image_by_id(id, index)
└─ ui_pic_set_image_index()
   ├─ ui_core_load_widget_info()    → 5× res_fread + 3× res_fseek
   └─ ui_core_load_imagelist() ×3   → 9× res_fread + 6× res_fseek
└─ ui_core_redraw()                   ← 合成在这儿，反而不是大头
```

**一次切图约 14 次读 + 9 次 seek**，打在资源文件上。元数据**不缓存**是设计使然 ——
资源管理器只有唯一一份 `static union ui_control_info` 缓冲（就是铁律 5 里那个），
所以每次都得重新读。

而 `res_fread()` 走哪条路由 `TCFG_UI_RES_MEDIUM` 决定：

| 配置 | `res_fread` 实际落到 | 相对成本 |
|---|---|---|
| `UI_RES_MEDIUM_INSIDE_FLASH` | `resfile_read()`，直接按偏移读 res 分区 | 低 |
| `UI_RES_MEDIUM_EXTERN_FLASH` | **`fread()`，过一遍 vfs + FAT + SFC** | 高 |

实测数据（240×240、16 根律动条、120ms 一拍、`EXTERN_FLASH` 配置）：

- 每次 `ui_pic_show_image_by_id()` ≈ **5.5ms**
- 16 根 × 8.3 拍/秒 × 23 次文件操作 ≈ **3000 次/秒**
- `ui` 任务因此长期占 **70~76% 的单核**，同页歌词渲染只占 3%

所以：

- **按拍刷多个控件的页面，先算这笔账再定刷新率和控件数**，别等上板发现
  `timer_no_response` 刷屏再回来改。
- "值没变就不刷"（`app.md` 要点 2）不是优化，是**必需**。
- 真要降载，按性价比是：切 `INSIDE_FLASH`（**整个 UI 都受益**，代价是烧写流程变）
  > 降刷新率 > 减控件数。

### ⚠ `ui_lock_layer()` / `ui_unlock_layer()` 在 br28 上是死代码

头文件（`ui.h`）写得像是"锁住图层批量画完再一次推给 IMB"，看着正好能解决上面
那个问题。**但它在这个平台上什么都不做。** 反编译 `ui_core.c.o`，两个函数结构
完全对称，都卡在同一个判断上：

```llvm
%4 = load i8, i8* %buf_num              ; dc->buf_num
%cmp13 = icmp eq i8 %4, 2               ; == 2 ?
br i1 %cmp13, label %land.lhs.true, label %cleanup   ; 不等就直接 return 0
```

而 `ui_platform.c` 里是 **`dc->buf_num = 1;` 写死**，全工程唯一一处赋值；
扫整个 `ui_new.a`，对 `draw_context` 这个字段的 15 处访问**全是 load、零 store**。
也就是双缓冲图层这条路在 br28 的平台层没实现，lock/unlock 永远走不进去。

（顺带说：就算能用也解决不了上面那个问题 —— 那笔开销在读资源元数据，
不在最后那次推送。）

## 8. 屏驱动怎么加一块新屏

一块屏一个 `.c`，放 `cpu/<芯片>/ui_driver/lcd_drive/lcd_spi/`（或 `lcd_mcu`/`lcd_rgb`）：

```c
#if TCFG_LCD_SPI_ST7789V_ENABLE          /* 板级配置里的开关 */

#define LCD_DRIVE_CONFIG  SPI_4WIRE_RGB565_1T8B

static const u8 lcd_cmd_t[] = { ...初始化命令序列... };
struct imd_param param_t   = { ...见上文... };

static void lcd_entersleep(void) { lcd_write_cmd(0x28, NULL, 0); lcd_write_cmd(0x10, NULL, 0); }
static void lcd_exitsleep(void)  { lcd_write_cmd(0x11, NULL, 0); ... }

REGISTER_LCD_DEVICE_NEW(st7789) = {
    .logo = "st7789v",
    .row_addr_align = 1,  .column_addr_align = 1,
    .lcd_cmd = (void *)&lcd_cmd_t,  .cmd_cnt = ARRAY_SIZE(lcd_cmd_t),
    .param   = (void *)&param_t,
    .reset = NULL,                    /* NULL = 用框架的通用复位 */
    .backlight_ctrl = NULL,
    .entersleep = lcd_entersleep,  .exitsleep = lcd_exitsleep,
};
#endif
```

注册同样走链接段（`ui.ld` 里的 `lcd_device_begin/end`、`lcd_interface_begin/end`）。

### ⚠ 屏的可视区不一定从 GRAM 原点开始

控制器的 GRAM 往往比面板大（典型：ST7789 的 GRAM 是 240×320，
240×280 的面板映射在 `y = 20..299`）。这时 `scr_y` 要写偏移量：

```c
#define SCR_X 0
#define SCR_Y 20      /* 不写偏移 → 顶部 20 行被截掉(画面上移)，底部 20 行不显示 */
#define SCR_W 240
#define SCR_H 280
```

同时初始化命令里的 `CASET`/`RASET`(0x2A/0x2B) 窗口也要按 `SCR_*` 推导，
别写死。

### 改分辨率要改三处，缺一处就对不上

| 改哪 | 改什么 |
|---|---|
| 屏驱动 `.c` | `SCR_W/H`、`LCD_W/H`、`SCR_X/Y`、`LCD_BLOCK_H`（重新算 RAM） |
| UI 工程 json | **每一页**的 `rect`（页 rect 就是屏尺寸），以及所有控件坐标 |
| `Application Data/ui-config` | `Size=宽*高`（GUI 画布尺寸，不改就只是编辑器里看着不对） |

三处对不上的症状：工具里排版正常、上板画面偏移或被裁、触摸命中区错位。

## 8.5 ⚠ 硬件加速器（FFT 这类）不能在 UI 上下文里调

**想在 UI 侧做频谱、滤波这类计算时会撞上这条。**

以 `JL_FFT` 为例，`hw_fft_run()` 内部是**忙等自旋**：

```c
while ((JL_FFT->CON & (1 << 7)) == 0);      /* 等硬件算完 */
```

在 UI 定时器回调里调它，**整个 ui 任务被拖住**，串口会刷：

```
timer_no_response: ui, ..., 100, ...        ← 两个 100ms 定时器同时不响应
```

根因是 `hw_fft.c` 里的三件事，每一条都能在源码里看到：

1. **那个自旋没有超时。** 模块没被使能时，完成标志永远不会置起来 ——
   循环就再也出不去。
2. **`FFT_CRITICAL_MODE == CRITICAL_SPIN_LOCK`**，自旋锁**不让出 CPU**。
   所以症状是调用它的任务被**整个饿死**，不是"变慢"或"掉帧"。
3. **使能权在音频侧**：`audio_setup.c` 的 `audio_disable_all()` 里有
   `JL_FFT->CON = BIT(1);  //置1强制关闭模块`。UI 侧根本管不到它的开关。

**正解：把计算搬到音频上下文**（如 `audio_effect_dev0_run`），
算完把结果写进一份缓存，UI 侧的定时器只负责把缓存刷到控件上 ——
正好就是 `app.md` 里那个"缓存置脏 + 定时器统一刷屏"的范式。

> **可复用的排查方向**：某个任务"再也不调度了"（而不是变慢），
> 就去找**无超时的硬件自旋等待** —— 尤其是那种使能权不在本模块手里的外设/协处理器。
> 这类代码在正常路径上跑得好好的，一旦模块没开就是死等。

## 8.6 排查手法：加一个 bypass 开关做二分

现象有两个以上嫌疑时，与其堆日志，不如**加一个编译期开关把其中一半摘掉**，
让用户烧一次就得到结论。

实例：`timer_no_response` 出现，嫌疑是「FFT 自旋」还是「16 个控件同时重绘」。
加一个：

```c
#define SPEC_DEBUG_NO_FFT   0   /* 置 1：跳过 FFT，用合成数据驱动控件 */
```

置 1 烧一次 —— 柱子正常显示、也不再报 `timer_no_response`，
**一次实验就砍掉一半范围**，结论是 FFT 那半。

比在两条路径上各加日志快得多，因为上板一轮的成本远高于改一行代码。
留着这个开关还能在以后回归时再用一次。

## 9. 常见现象 → 先查哪

| 现象 | 先查 |
|---|---|
| 整页只剩一两个控件 | 绘制期回调里直接调了 UI 更新 API（app.md 头号坑） |
| 界面能画但按键没反应 | action 文件没进编译 / `STYLE_NAME` 没定义 / 弹层排在主布局之前 |
| 图标周围一圈黑底 | `image-type` 用了 `RGB565`，该用 `ARGB8565` |
| 某控件把下面盖住了 | 它的 `background_color` 不是空串/`#ffffffff` |
| 画面整体偏移或底部少一条 | 屏驱动 `SCR_X/SCR_Y` 没按面板在 GRAM 里的位置写 |
| 换了工程后所有控件都找不到 | ID 头和资源不是同一次导出的（export.md） |
| 刷新卡顿/费电 | 常驻页面上有滚动文字或 `play_mode` 轮播图；控件太多 |
| 开了特效就死机/花屏 | 没有 PSRAM（`ENABLE_PSRAM_UI_FRAME == 0`）却用了整帧特效 |

## 10. 查框架实际行为的办法

库是 LLVM bitcode，可以反编译成可读 IR（带 debug info）：

```sh
export PATH=/c/JL/pi32/bin:$PATH
cd <临时目录>
cp <SDK>/cpu/<芯片>/liba/ui_new.a .
llvm-ar.exe t ui_new.a                       # 看有哪些编译单元
llvm-ar.exe x ui_new.a ui_core.c.o
opt.exe -S ui_core.c.o -o ui_core.ll         # 没有 llvm-dis，用 opt -S
grep -n "define.*ui_core_show_rect" ui_core.ll
```

`ui_new.a` 里有 `ui_core` `layer` `layout` `window` `ui_pic` `ui_text` `ui_grid`
`imb` `imd` `imd_spi` `lcd_buffer_manager` `scale` `resize` `imb_effect` 等。
本篇和 app.md 里几处"框架实际怎么做"的结论就是这么确认的 ——
**拿不准的行为，去读 IR，别猜**。

### 定位一个"控件行为不对"的标准路径

实例：用户报"暂停键有反应、上一首下一首没反应"，怀疑某个控件把键吃了。

```sh
export PATH=/c/JL/pi32/bin:$PATH
llvm-ar.exe t ui_new.a | grep -i slider              # ① 找到是哪个 .o
llvm-ar.exe x ui_new.a ui_slider.c.o
opt.exe -S ui_slider.c.o -o ui_slider.ll             # ② 转 IR
grep -nE "^define [^@]*@[a-zA-Z_0-9]+" ui_slider.ll  # ③ 列出函数名
awk '/define internal i32 @slider_onkey/,/^}/' ui_slider.ll   # ④ 读那一个
```

④ 里直接就能看到 `switch i8 %4 [ i8 37 … i8 40 … ]` 和返回值 ——
**一次就定位到"slider 消费方向键"**，比在设备上二分测试快得多。

带 debug info，所以还能顺着 `!dbg` 找到源码行号；
`@xxx_event_handler` 这类全局常量里能直接看到控件注册了哪些回调。

### 技巧：读 `onkey`/`onchange` 这类函数，直接看返回值的 `phi`

这套框架的事件回调**语义几乎全在返回值上**（返回非 0 = 消费掉、中止分发）。
所以与其顺着控制流读，不如直接找返回值那行 `phi`，一眼看全所有出口：

```llvm
%retval.0 = phi i32 [ 1, %for.end ], [ 1, %if.then ], [ 0, %sw.bb ], [ 0, %if.end5 ]
```

四个入边就是四种情形，回头对一下各自来自哪个块即可 ——
`slider_onkey` 那张"什么时候返回 1、什么时候返回 0"的表就是这么一行读出来的，
比逐块跟快得多。
