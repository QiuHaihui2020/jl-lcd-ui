---
name: jl-lcd-ui
description: 杰理(JL)彩屏 UI 框架的界面开发，图层走 OSD16、设备端由 IMB 硬件合成。做界面布局（直接编辑 .uiproj/.json 工程脚本）、选控件、给控件写应用层回调、生成并导出资源、适配新屏和新分辨率时用。涉及 LCD_UI工程/UITools GUI 工具链、控件库 control.json、控件 ID 位域规则、REGISTER_UI_EVENT_HANDLER 事件注册、ename.h/style_JL_new.h 绑定、JL.sty/JL.res/JL.str 产物、SPI/MCU/RGB 屏驱动（st7789 等）。不适用于单色点阵屏（OSD1，那套看 jl-dot-ui）。
---

# 杰理彩屏 UI 开发

适用范围：**杰理(JL) SDK 里走 `ui_framework` + UITools 的彩屏 UI**。
硬约束是图层 `color_format = OSD16`，设备端由 **IMB 硬件图层合成**出帧再推屏，
和单色点阵屏（`OSD1`，软件 framebuffer）是两条完全不同的路径。

资源产物叫 `JL.sty` / `JL.res` / `JL.str`，应用侧 ID 头一般叫 `style_JL_new.h`
（名字随 SDK 版本略有出入，看工程 `copy_file.bat` 拷到哪个文件）。

```
工程脚本 .json  ──UITools(GUI)──►  JL.sty/res/str  ──►  设备端 ui_framework + IMB ──► SPI/MCU/RGB 屏
      ▲                                  │
      └── 你在这里排版                    └── ID 头 ──► action 代码挂回调、调控件 API
```

**分辨率、页数、模式都不限死**：屏幕尺寸是每个工程自己的（页节点的 `rect`），
文档里的坐标例子按本仓库样例的 240×240 写，换个尺寸这套照样用，只是数字不同。

## 一个彩屏工程由哪些东西组成

| 东西 | 典型路径（本仓库的实例） |
|---|---|
| UI 工程（可以有多个） | `cpu/<芯片>/tools/LCD_UI工程/<工程>/<界面>/project/<名字>.json`<br>本仓库：`ui_128_64_JL02/…/SmallColorTFT.json`（11 页，固件在用）<br>　　　　`ui_240x240_soundbox/…/BT_Watch.json`（6 页，手表 demo） |
| GUI 工具链（工程共用） | `…/LCD_UI工程/UITools/`（`ui-tools.exe` 画界面，`QtToolBin.exe` 生成资源） |
| 应用代码 | `apps/<产品>/ui/lcd/<STYLE>/*.c`，一页一个 action 文件<br>本仓库：`apps/soundbox/ui/lcd/STYLE_SOUNDBOX/`（14 个） |
| ID 头（自动生成，勿手改） | 工程里的 `ename.h` → 拷成 `apps/soundbox/include/ui/style_JL_new.h` |
| 业务别名（手写，进版本库） | `apps/soundbox/include/ui/ui_style.h`：`ID_WINDOW_BT` → `PAGE_1` |
| 框架头文件 | `interface/ui/jl_ui/ui/*.h`；实现是 bitcode 库 `cpu/<芯片>/liba/ui_new.a` |
| 平台层（有源码） | `cpu/<芯片>/ui_driver/interface/ui_platform.c`、`…/lcd_drive/` |
| 资源落地 | `cpu/<芯片>/tools/JL_LCD/{JL.sty,JL.res,JL.str}` → 烧录时打包成 res 分区 |

> ⚠ **别按目录名挑工程**。本仓库 `ui_128_64_JL02` 里装的是 **240×240 彩屏**工程
> （`SmallColorTFT.json`），名字是历史遗留。认准 `copy_file.bat` 的目标路径
> 和页节点 rect，别认目录名。

## 和 jl-dot-ui（单色点阵屏）的关系

两个 skill 讲的是**同一家的两套不同框架**，好几条结论是**相反的**，
照着点阵那套写彩屏会踩坑：

| | jl-dot-ui（点阵） | 本 skill（彩屏） |
|---|---|---|
| 图层 `color_format` | 必须 `OSD1` | 必须 `OSD16` |
| 设备端绘制 | 软件逐点写 1bpp framebuffer | **IMB 硬件合成任务**，每个控件一个 task |
| 事件注册 | 显式表 + `ui_port_registry.c`，**禁用** `REGISTER_UI_EVENT_HANDLER` | **必须**用 `REGISTER_UI_EVENT_HANDLER`（`ui.ld` 里有段） |
| 背景填充语义 | 三态：透明 / 点亮 / **擦灭** | 两态：不填充 / 填一块不透明色 |
| 工具 | 有定制 CLI（`--gen`/`--shot`/`--json-roundtrip`） | **只有 GUI**，没有可脚本化的命令行 |

其余（json 树形状、`caption` 决定类型码、坐标相对父节点、控件生命周期、
`ui_set_call` 那个坑）两边是一样的，可以互相参考。

---

## 工作循环

**这套工具链没有命令行**（`ui-tools.exe` / `QtToolBin.exe` 都是 Qt GUI，
只有 `style_table.exe` 有 CLI，而它只做最后给 `.sty` 加工程号那一步）。
所以循环是「AI 改脚本 + 人工点两下导出」：

```
① 看懂现状     tools/dump_tree.py <工程.json> -p <页号> [-v]
                   ↓
② 改 .json     直接编辑（就是 JSON），排版/加控件/改可见性
                   ↓   ⚠ 脚本回写必须 newline='\n' + ensure_ascii=False
                   ↓      + indent=4 + sort_keys=True，否则 10MB 文件全量 diff
                   ↓      （模板见 reference/project.md 第 0 节）
③ 体检         tools/check_project.py <工程.json>      ← 有 ERROR 就回去改
                   ↓
④ 先算 ID      tools/gen_ename.py <工程.json> --check <应用侧 ID 头.h>
                   ↓                       本仓库是 apps/soundbox/include/ui/style_JL_new.h
                   ↓                       输出告诉你哪些 ID 变了/新增了/头文件里多出来了
⑤ 写应用代码   <产品>/ui/lcd/<STYLE>/<页>_action.c
                   ↓
⑥ 人工导出     step1 打开绘图工具 → 保存 → step2 资源生成工具 → 生成
                 → project 目录下 copy_file.bat（见 reference/export.md）
                   ↓
⑦ 编译烧录     资源进 JL_LCD/，download.bat 打包成 res 分区
```

第 ④ 步是这套 skill 的关键：**控件 ID 是纯算出来的**（规则见下），
所以不用等人工导出就能接着写代码；`--check` 还能立刻告诉你
「应用代码里引用的某个 ename 已经在工程里没了」。

⚠ **第 ⑥ 步只能人工做，而且它会直接改固件树。** AI 不要去调 `.exe`。
⚠ **两个工程的 `copy_file.bat` 写的是同一个目标**（`JL_LCD/` 和 `style_JL_new.h`）。
   在 BT_Watch 里点一次「资源生成」，固件资源就被手表 demo 换掉了。

### ⚠⚠ 改 json 之前先确认 GUI 已经关了

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

## 铁律

### 1. 控件 ID 是位域，算得出来

设备端 `control.h` 给了三个官方宏，反过来就是 ID 的构成：

```c
ui_id2prj(id)  = (id >> 26) & 0x3f    // 工程号，UI 编译工具里设，本仓库两个工程都是 0
ui_id2page(id) = (id >> 17) & 0x1ff   // 页在 pages[] 里的下标
ui_id2type(id) = (id >> 10) & 0x7f    // 控件类型码 CTRL_TYPE_*
低 10 位                               // 同页同类型内的序号，按页内遍历顺序从 0 递增
```

例：`BT_LAYER = 0x21000` = 页 1 | 类型 4(LAYER) | 序号 0。
`PAGE_n` 自己是 `页n | 类型 2(WINDOW) | 序号 n`。

`tools/gen_ename.py` 就是照这个算的，拿仓库两个工程标定过（572 个 ID 全中，0 不一致）。

**推论：往一页中间插一个控件，会把它后面同类型控件的序号全推后一位 ——
那些控件的 ID 全变。** 所以插控件之后一定要跑一次 `--check`，
再按输出去改应用代码里的 ename。加在**页末尾**则不影响已有 ID。

### 1.2 示例一律从工程里真实存在的值取，不要自己编

**错误的示例比没有示例更危险** —— 读者会优先照抄示例，而不是去翻工程里的现成写法。

这条是血的教训：本 skill 早期版本按 printf 的直觉编了个 `format: "y-m-d"`
当日期示例，实际上 Time 的 format 里小写 `m` 是**分钟**、`y`/`d` 根本不是字段。
照着写的人做出来的日期控件显示的是分钟数，上板才发现 —— **文档主动制造了一个 bug**。

所以：

- 写任何属性示例前，先 `grep` 工程里这个属性的真实取值，从中挑一个。
- 各篇里那些「现成范例在哪一页」的表就是为这个存在的，**用它们**。
- 拿不准的值宁可不给示例，只写规则。

### 反过来也成立：**"工程里存在"不等于"正确"**

现成写法可以当参考，但不能闭眼抄。本 skill 已知的几个"大量存在但不该学"的实例：

| 工程里的现状 | 为什么不该抄 |
|---|---|
| `background_color: "#ffffffff"`（443 处） | 编辑器里画成不透明白，要透明得写空串（铁律 4） |
| 控件库默认色 `#8DEEDB` `#D2EE45` 等原样留着 | 是有效颜色，会被真的画出来 |
| 页 2 `FM_SLIDER` 的零件只有本体 87.5% 宽 | 那个实例**碰巧看不出问题**（零件没配图），照抄再配上图就错位（`project.md`） |
| 系统页几个弹层排在主布局**之前** | 不享受"自动抢占按键"（`authoring.md`） |

所以凡是"现有工程这么写但你不该学"的地方，本 skill 都会明说。
**遇到本 skill 没提、而工程里写法不一致的，以本 skill 查证过的规则为准，
或者去反编译确认 —— 不要少数服从多数。**

### 1.5 几条"不知道就会做错"的硬规则

排版/写代码之前先扫一眼，每条都在对应的 reference 里有完整说明：

| 规则 | 详见 |
|---|---|
| Time 的 `format` **区分大小写**：`Y M D` 是年月日、`h m s` 是时分秒；<br>写 `y-m-d` 是错的（小写 m 是分钟） | `project.md` |
| Time/Number 的分隔符**按出现顺序**取 `delimiter.list[0][1][2]`，<br>和写的是 `:` 还是 `-` 无关 | `project.md` |
| Number 内部是 **u16**，范围 0..65535，**显示不了负数**（-4 会变 65532） | `widgets.md` |
| Text 的 `code` 属性**决定能调哪组 API**，排版时就定死 | `widgets.md` |
| **strpic 的字号在 xls 单元格里**，改 `ResBuilder.xml` 的 `<Fonts>` 没用<br>（改错了还会像改对了：工具预览会变，`JL.str` 一个字节不变） | `platform.md` |
| 列表的**行高/间距是节点顶层的 `sizehw`/`space`**，翻 `property[]` 找不到；<br>它们和条目 rect 必须一起改 | `widgets.md` |
| 框架**不拷贝字符串**，`ui_text_set_*` 传的 buf 必须是全局/静态 | `widgets.md` |
| 要透明必须 **RGBA PNG + `ARGB8565`**，代价是 +50% 资源 | `platform.md` |
| 框架**不缩放图片**，图比 rect 大就被裁 | `platform.md` |
| 固定文案和运行时文字是**两套独立机制**；**运行时不变的文字一律加进多国语言表<br>用 Text+strpic，不要渲染成图**（`.xls` 能用 Excel COM 自动加行，不必人工） | `platform.md` / `export.md` |
| `check_project.py` **不查** `str.list` 的 id 在不在语言表里，<br>写了个不存在的 id 不报错、运行时那条是空白 | `export.md` |
| `ui_get_disp_status_by_id()` 返回 1/0/-14，**头文件注释是反的** | `app.md` |
| 它还**判不出"被同页弹层盖住"**（弹层不会 hide 主布局），<br>遮挡只能由弹层在 `ON_CHANGE_SHOW/HIDE` 里自己告知 | `app.md` |
| 弹层的显示/隐藏配对**只能用 `ON_CHANGE_SHOW/HIDE`**；<br>`INIT` 只发一次、`RELEASE` 只在销毁时发，用错 = 第一次弹窗后再也不恢复 | `app.md` |
| 被盖住的控件**刷屏不但没用还更贵**（要连带重新合成上面的弹层） | `app.md` |
| **每次 `ui_pic_show_image_by_id()` 要重读 ~14 次资源文件**（元数据不缓存）；<br>按拍刷多个控件之前先算这笔账 | `platform.md` |
| `ui_lock_layer()` / `ui_unlock_layer()` 在 br28 上是**死代码**（`dc->buf_num` 写死 1） | `platform.md` |
| Text 两个同名 `color` 里**第二个是选中高亮色**，去重时合并会静默丢掉高亮；<br>两项写成同值也一样没高亮（本仓库约定 常态 `#ffa6b8d8` / 高亮 `#ffffffff`） | `widgets.md` |
| **布局/图片/文字/时间都可以带两份 `element_css`**，第二份是高亮态，选中时框架<br>整份换掉（`rect` 也在里面）。这是做**整行高亮**的正路，**应用代码一行不用写**；<br>两份的差异只该在 `background_color`(直角) 或 `background_image`(可圆角)。<br>`ui-tools` 只编辑第一份，GUI 里挪过位置就会错位，症状是"一选中控件就跳走" | `widgets.md` |
| `RING_MAX_TASK=40` 不是控件数上限，是任务块缓存大小 | `platform.md` |
| **Text 默认是黑字**，改页面底色必须同时扫一遍这页所有 Text 的 color | `widgets.md` |
| **slider 会吃掉方向键**（37/38/39/40），按键驱动的页面放进度条必踩 | `widgets.md` |
| **vslider 是"满格在上"**：`persent` 越大滑块越靠上（100 在顶、0 在底）。<br>文件列表这类"越往下翻滑块越往下"要**取反**；而且 `persent` 默认 0 就是最底，<br>框架不给初值，得在"刷新列表内容"那个函数里主动设 | `widgets.md` |
| vslider 零件的**绘制顺序：槽必须排在滑块前面**（数组靠后画在上面）。<br>仓库原来是反的，能用只因老槽图大部分透明、滑块从两侧露出来 | `widgets.md` |
| 列表里"只让选中那行滚动"**别指望 `FONT_HIGHLIGHT_SCROLL`** —— 它只在<br>`ON_CHANGE_HIGHLIGHT` 里起 timer，而 grid 自己切光标时高亮位已经变过了，<br>`ui_core_highlight_element()` 开头就 return，事件根本不发。<br>改用 `FONT_SHOW_SCROLL` 由应用层自己决定哪行滚 | `widgets.md` |
| 定时器/按键回调里**不要调音频侧的硬件加速接口**（FFT 等），会饿死整个 UI 任务 | `platform.md` |
| 加新 `.c` 改的是 `build/genFileList.c`，不是 `build/fileList.c` | `app.md` |

### 2. `caption` 决定控件类型，不是 `-type`

slider / vslider / watch / compass / progressbar 是**组合控件**，
零件的 `-type` 全是 `ImageList`，靠 `caption` 是 `right_pic` / `left_pic` /
`slider_pic` 才被认成滑条零件（类型码 29/30/31）。

**不要"顺手整理" caption** —— 改了就静默退化成普通图片，不报错，
而且因为类型码变了，**整页同类型控件的 ID 序号会跟着错位**。
`check_project.py` 会检查零件是否齐全。

### 3. 图层的 `color_format` 必须是 `OSD16`

`OSD1` 是单色点阵屏那条路径（`DC_DATA_FORMAT_MONO`）。彩屏工程选了它，
设备端会走 1bpp 的画点逻辑，屏上基本是花的。
两个工程的全部 17 个图层都是 `OSD16`，新建图层照抄。

### 4. 背景填充只有两态，别留控件库默认色

框架画一个控件时（`ui_core.c` 的 `ui_core_show_rect`，反编译自 `ui_new.a` 的 bitcode）：

```
if ((css.background_color & 0xFFFFFF) != 0xFFFFFF)
        platform_api->fill_rect(dc, background_color);   // 先填一块不透明色
draw 背景图 / 边框 / 内容
```

彩屏的 `fill_rect` 落到 `ui_platform.c` 的 `br28_fill_rect()` → `imb_create_color()`，
**生成一个纯色 IMB 任务盖在下面**。所以：

| json 里的 `background_color` | 设备端 | **ui-tools 编辑器预览** |
|---|---|---|
| 空串 `""` | 不填充 —— 透明，露出下层 | 不填充 ✅ **两边一致** |
| `#ffffffff` | 不填充 | **画成一块不透明白** ❌ 两边不一致 |
| 其它任何颜色 | **填一整块不透明色**，盖住下面 | 填充 |

### ⚠ 要透明**只能写空串**，别照抄现有工程的 `#ffffffff`

这是个"照抄现成写法反而踩坑"的地方：样例工程 `SmallColorTFT` 里
**443 个控件写的是 `#ffffffff`**，照着抄完全合理 —— 但那样在编辑器里
预览是**整页白**，只有上板才正常。空串则两边都对
（`BT_Watch` 有 11 处空串，证明工具支持并会保留）。

设备端为什么两者等价，从 bitcode 能看出来（`#ffffffff & 0xFFFFFF == 0xFFFFFF`
→ 不 fill）；编辑器那半边是闭源 GUI，属于实测结论。
**所以：新建/修改控件一律写空串。**

> ⚠ 上表"设备端 `#ffffffff` = 不填充"这一格**在 BR28 + ST7789 这版上量下来是错的**：
> 传到 `br28_fill_rect()` 的已经不是 24 位裸色（低 16 位才是 RGB565），代回判据
> 得到的是"照样 fill，填成白"。屏上那块白是肉眼可见的。
> 详见 `reference/platform.md` §5 的实测记录，那里也写了怎么在自己这版上复验。
> **不影响结论**：空串在两套说法下都是不填充，所以还是一律写空串。

⚠ 控件库模板自带的 6 位默认色（`#8DEEDB` `#D2EE45` `#D9EE94` `#368FEE` `#EED9C1`）
在工具里看着像"没设过"，但它们**是有效颜色**，两边都会画出来。
从控件库 deepcopy 建节点时要么改成空串，要么主动挑一个颜色。

> 这不是假想的风险：`BT_Watch` 在编辑器里能看到一片蓝/黄绿/粉的色块，
> 就是 `#368FEE`×10、`#D2EE45`×8、`#D9EE94`×8、`#EED9C1`×3
> 这些控件库默认色原样留着被画出来了 —— **官方样例工程自己也没躲过这一条**。

`check_project.py` 会把控件库默认色和 `#ffffffff` 都列出来。

### 5. 绘制期回调里不能调 UI 更新 API

`ON_CHANGE_SHOW_PROBE / SHOW / SHOW_POST / FIRST_SHOW / SHOW_COMPLETED`
都是**在绘制过程中**发的。在里面调 `ui_pic_show_image_by_id()` /
`ui_text_set_*` / `ui_number_update_by_id()` 会重入整套绘制递归，
还会冲掉资源管理器里唯一那份 `static union ui_control_info` —— 症状是整棵子树画不出来。

**`ON_CHANGE_INIT` 也算在内**（实测踩过）。它虽然不在上面那 5 个里，但它是在
建页面这趟遍历中发的，此时**兄弟控件可能已经建好了** —— 对它们调 `*_by_id()`
一样会真的触发重绘、一样冲掉那份 static 缓冲。分界不是事件名，是
**"碰不碰别的控件"**：

| 在 `ON_CHANGE_INIT` 里 | 行不行 |
|---|---|
| `ui_pic_set_image_index(pic, 1)` 改**自己**（拿到的是 `ctr` 句柄） | ✅ 只写字段，不重绘 |
| `ui_battery_set_level(battery, ...)` 改**自己** | ✅ 同上 |
| `ui_register_msg_handler()` / `sys_timer_add()` / 申请页面私有状态 | ✅ 不碰控件 |
| `ui_pic_show_image_by_id(别的控件, n)` | ❌ 跨控件刷新 → 重入绘制 |

要在 INIT 里刷别的控件，走 `ui_set_call()`，或者干脆交给定时器第一拍。

正解是框架自带的 `ui_set_call(cb, 0)`，把刷界面推迟到本轮事件分发结束：

```c
case ON_CHANGE_FIRST_SHOW:
    ui_set_call(vol_init, 0);    /* 不要在这里直接调 ui_xxx_set/show */
    break;
```

反过来，**在消息回调 / 定时器 / 按键处理里必须直接调**，
那里 `ui_set_call()` 的上下文句柄是空的，调用会被静默丢弃。
`bt_action.c` 两种写法都有，并且把理由注释出来了。详见 `reference/app.md`。

### 6. 事件注册用 `REGISTER_UI_EVENT_HANDLER`，别照搬 jl-dot-ui 的显式表

本仓库 `interface/ui/jl_ui/ui/ui.ld` 里有段边界符号
（`elm_event_handler_begin_JL` / `..._end_JL`），链接段收集是有效的：

```c
#define STYLE_NAME  JL          /* 每个 action 文件顶部都要有 */
REGISTER_UI_STYLE(STYLE_NAME)   /* 整个 style 注册一次即可 */

static int bt_win_onchange(void *ctrl, enum element_change_event e, void *arg) { ... }
REGISTER_UI_EVENT_HANDLER(ID_WINDOW_BT)
.onchange = bt_win_onchange,
 .ontouch = NULL,
};
```

注意那个宏**不是完整语句**——它展开成结构体初始化的前半截，
所以后面直接跟成员赋值，再用 `};` 收尾。照抄现有 action 文件的形状。

### 7. 一个页一个图层，弹层靠 `invisible` 的布局

两个工程都是「一页 = 一个 `NewLayer` = 整屏」，页内用多个 `NewLayout` 分主界面和弹层，
弹层默认 `invisible: true`。按键分发是**子元素从尾往前**，
所以弹层排在主布局**之后**就能先拿到按键，不用写"菜单开着就不处理"的判断。

### 8. 改屏分辨率是三处一起改

屏驱动（`lcd_spi_*.c` 的 `SCR_*`/`LCD_*`）、工程里**每一页**的 `rect`、
`Application Data/ui-config` 的 `Size=宽*高`。
三处对不上时，工具预览、实机、按键命中区会各说各话。详见 `reference/export.md`。

---

## 可用控件

| caption | -type | 类型码 | 应用侧头文件 |
|---|---|---|---|
| 页面 | page | 2 | `UI_SHOW_WINDOW()` / `UI_HIDE_WINDOW()` |
| 布局 | NewLayout | 3 | ——（结构节点，可注册回调） |
| 图层 | NewLayer | 4 | ——（结构节点，可注册回调） |
| 垂直列表 / 水平列表 / 表格控件 | VerticalList / HorizontalList / NewGrid | 5 | `ui/ui_grid.h` |
| 图片 | ImageList | 8 | `ui/ui_pic.h` |
| 电池电量 | Battery | 9 | `ui/ui_battery.h` |
| 时间 | Time | 10 | `ui/ui_time.h` |
| 文字 | Text | 12 | `ui/ui_text.h` |
| 数字 | Number | 15 | `ui/ui_number.h` |
| slider / vslider | （组合控件，控件库 `control/ex/`） | 28 / 33 | `ui/ui_slider.h`、`ui/ui_slider_vert.h` |
| progressbar / multiprogressbar | （组合控件） | 20 / 22 | `ui/ui_progress.h`、`ui/ui_progress_multi.h` |
| watch / compass | （组合控件） | 24 / 38 | `ui/ui_watch.h`、`ui/ui_compass.h` |

⚠ 控件库 `control.json` 里只有 11 个基本控件，`Button`(7) 在库里但设备端没做实现；
组合控件在 `control/ex/*.json`。`Camera`(11) `animation`(13) `player`(14) 不要用。

彩屏比点阵多出来的能力（都在 `interface/ui/jl_ui/ui/` 里有头文件）：
页面滑动切换 `ui_page_switch.h`、转场特效 `ui_effect.h`、图片旋转 `ui_rotate.h`、
文件浏览 `ui_browser.h`、歌词 `lyrics.h`、Lua 脚本（每个控件都有 `luascript` 属性）。

---

## 参考资料（按需读，别一次全看）

| 文件 | 什么时候读 |
|---|---|
| `reference/assets.md` | **做素材**。字号怎么定、量参考图、透视校正、取色、改图后要同步改什么 |
| `reference/widgets.md` | **选控件**。每个控件什么时候用、限制、代码怎么调；含"两个都能做时选哪个" |
| `reference/authoring.md` | **建工程 / 搭结构**。工程目录、从控件库造节点、什么时候建页/图层/布局、弹层怎么做 |
| `reference/project.md` | **改 json**。树结构、类型码、ID 规则、坐标、各类属性怎么写 |
| `reference/app.md` | **写代码**。事件注册、生命周期、各控件 API、窗口/弹层/消息/按键 |
| `reference/platform.md` | **查现象**。IMB 硬件合成、图层 buffer、图片格式、屏驱动、分辨率、性能 |
| `reference/export.md` | **导出/烧录**。GUI 两步、copy_file.bat、res 分区打包、多国语言表 |

排一个新界面的顺序：`widgets.md` 选控件 → `authoring.md` 搭结构 →
`project.md` 落成 json → `assets.md` 做图 → `app.md` 写回调 → `export.md` 导出。

> ⚠ **要动哪个控件，就把 `widgets.md` 里那个控件那一节读完。**
> 实战里为了改列表行高，只读了 Text 一节就去改条目 rect，
> 而 `sizehw`/`space` 就写在同一个文件的列表一节里 ——
> 结果绕了一大圈去反编译，还改漏了参数。
> 按关键词 grep 比按行号截一段读更靠谱。

## 随 skill 带的三个脚本

```
tools/dump_tree.py      把几 MB 的工程 json 打成可读的树（带算出来的 ID）
tools/check_project.py  语义体检，有错误返回 1
tools/gen_ename.py      从 json 算 ename.h；--check 和现有 style_JL_new.h 比对
tools/render_page.py    从 json 渲染整页做排版自检（★ 需要 pillow）
tools/jlui.py           公共解析层（类型码表、遍历、ID 计算、图片/格式解析）
```

前三个 + jlui **零依赖**，`render_page.py` 需要 `pip install pillow`
（它本质是图像合成，自己解码再做 alpha 合成不值当）。

`check_project.py` 和 `gen_ename.py` 都拿仓库里两个真实工程标定过
（0 错误 / 572 个 ID 全中），**它们一旦报错就是真错**。

> 库是 LLVM bitcode（`cpu/br28/liba/*.a`），要查框架实际行为可以反编译：
> ```
> export PATH=/c/JL/pi32/bin:$PATH
> llvm-ar.exe x ui_new.a ui_core.c.o && opt.exe -S ui_core.c.o -o ui_core.ll
> ```
> 带 debug info，函数名和源码行号都在。本文第 4 条的绘制顺序就是这么确认的。
