# 建工程 · 组织界面

本篇讲的是杰理彩屏 UI 工具链的通用做法。文中凡是「样例工程」都指
本仓库 `LCD_UI工程/` 下那两个（`SmallColorTFT.json` 11 页 499 控件、
`BT_Watch.json` 6 页 56 控件），它们只是**用来标定规律的样本**，
换个 SDK、换个分辨率，规律一样成立，数字不同。

---

# 一、工程目录长什么样

杰理发布的 SDK 里，彩屏 UI 工程都是这个形状（目录名各版本略有出入）：

```
<SDK>/cpu/<芯片>/tools/LCD_UI工程/
    UITools/                         ← 工具链，所有工程共用
        ui-tools.exe                 画界面（GUI）
        QtToolBin.exe                资源生成（GUI）
        style_table.exe              给 .sty 加工程号（有 CLI）
        ResBuilder.exe / Resbuilder.xml / Resbuilder.dat
        control/control.json         控件库（11 个基本控件）
        control/ex/*.json            组合控件库（slider/vslider/watch/compass/progressbar）
        多国语言_*.xls               文字表
        UI工程源文件升级工具.exe      老工程升级到新工具版本
    <工程A>/<界面名>/
        step1-打开UI绘图工具.bat
        step2-打开UI资源生成工具.bat
        打开图片资源文件夹.bat  打开多国语言表格.bat
        project/
            <工程名>.json            ← 工程脚本，你改的就是它
            Application Data/ui-config   编辑器设置(含 Size=宽*高)
            config/                  图片资源，按子目录组织
            ename.h                  控件 ID 头（生成物）
            copy_file.bat            把产物拷进固件树
            ResBuilder.xml           打包配置（图片清单/颜色表/excel 路径；
                                     里面的 <Fonts> 不是 strpic 字号，别改它）
            project.bin result.bin result.str  ← 生成物
    <工程B>/...                      同一套工具下可以有多个工程
```

**一套工具下可以挂多个工程**（模式界面、表盘界面、侧边栏各一个）。
它们靠 ID 里的**工程号**（`id >> 26`）区分，工程号在资源生成工具里设，
由 `style_table.exe -prj 0xN` 写进 `.sty`。

⚠ **同一套工具下的多个工程，`copy_file.bat` 往往写的是同一个目标路径。**
在 B 工程里点一次「资源生成」，固件用的就变成 B 的界面了。
动手前先确认自己在哪个工程目录里。

---

# 二、从零建一个工程

工具没有「新建工程」的命令行。两条路：

| 做法 | 怎么做 |
|---|---|
| **复制一个现成工程**（推荐） | 拷贝整个 `<工程>/` 目录 → 清掉 `config/` 里不要的图 → 用脚本把 `pages[]` 删到只剩需要的 → 改 `Application Data/ui-config` 的 `Size` 和 `LastOpen` |
| GUI 新建 | 开 `ui-tools.exe`，菜单里新建，然后逐个拖控件 |

**别手写空工程的 json。** 每个节点都要带一整套控件库模板字段
（`property` 的项数、顺序、默认值全都有讲究），少一项工具就不认，
而且多半不报错、只是那个控件画不出来。

## 加控件：从控件库 deepcopy

新控件的正确来源是控件库，不是手敲：

```python
import json, copy
LIB = {c['caption']: c for c in
       json.load(open('UITools/control/control.json', encoding='utf-8'))['compoents']}
# 组合控件在 UITools/control/ex/*.json，各自是一棵完整子树
node = copy.deepcopy(LIB['图片'])
```

deepcopy 之后**必须改这四样**：

1. `property` 里 `id.ename` —— 起业务名，全工程唯一（**这是应用代码唯一的抓手**）
2. `element_css.rect` —— 坐标相对父节点
3. `element_css.background_color` —— 控件库默认是 6 位彩色，
   **想透明就清成空串**，否则是一块不透明色（SKILL.md 铁律 4）
4. `-name` —— 编辑器里显示的名字，随意，但别和别人重名太混乱

### 用表驱动的脚本，别一个个手写

每个控件一行，`ename` 作为**必填位置参数**，漏写直接报错 ——
比"记得填 ename"这种提醒硬得多：

```python
# (控件, ename, rect, 图集/文字, 说明)
WIDGETS = [
    ("电池电量", "BT_BAT",        (210,  0,  30, 30), BATT_FRAMES, "右上角电量"),
    ("图片",     "BT_STATUS_PIC", ( 75,  0,  90, 30), STATUS_FRAMES, "连接/断开"),
    ("文字",     "BT_MUSIC_NAME", (  0, 60, 240, 30), ["m10"],      "歌名"),
]

def make(kind, ename, rect, data, note):   # ename 漏了就 TypeError
    node = copy.deepcopy(LIB[kind])
    ...
```

> 写生成脚本时**用 Write 工具落盘再跑**，不要塞进 bash heredoc ——
> heredoc 会吃掉反斜杠、被脚本里的引号绊住，而且失败得很隐蔽。

## 改完的自检顺序

```
python tools/check_project.py <工程.json>                       # 语义
python tools/gen_ename.py   <工程.json> --check <现有ID头.h>     # ID 有没有变
python tools/dump_tree.py   <工程.json> -p <页号>                # 眼看结构
```

**排版对不对最终只能靠 GUI 预览或上板**，这套工具链没有出图的命令行
（不像点阵那套有 `--shot`）。所以：能算的先算干净，别把可以静态发现的问题
留到上板阶段。

---

# 三、界面怎么组织：什么时候建页 / 图层 / 布局

下面的规律是把样例工程逐页统计出来的。新建界面照这个来，
和既有工程、应用代码的结构才对得上。

## 一句话决策

| 你要做的 | 建什么 |
|---|---|
| 一个新的**工作模式**（蓝牙、FM、时钟、设置…），和别的模式互斥 | **新建一页** |
| 同一模式里的**弹层**（音量条、菜单、来电提示） | 在本页图层下**新建一个整屏布局**，默认 `invisible` |
| 同一功能键下的**翻页** | **不要新建页**，同上，靠 `invisible` 切 |
| 把几个控件**当一组**摆放/整体显示隐藏 | **嵌套一个布局** |
| 列表的**一行/一格**长什么样 | 列表的 `listwidget[]` 里放**一个布局** |
| 别的 | **不要**建新图层 —— 见下 |

## 页（`ScenesScreen`）= 一个工作模式

样例工程 11 页，一页一个模式：

```
页0 菜单   页1 蓝牙   页2 FM     页3 时钟   页4 音乐   页5 开机
页6 关机   页7 系统设置  页8 PC(声卡)  页9 LINE-IN  页10 录音
```

- 页之间**互斥**，同一时刻只显示一页。
- 页 ID 是 `PAGE_0` `PAGE_1` …，**按页在 `pages[]` 里的顺序生成**。
  **插入或调整页顺序会改掉后面所有页的编号**，`ui_style.h` 里
  `#define ID_WINDOW_BT PAGE_1` 这类映射要跟着改。**尽量往后追加。**
- 切页用 `UI_SHOW_WINDOW(ID_WINDOW_BT)` / `UI_HIDE_CURR_WINDOW()`。
- 一页对应一个 `<模式>_action.c`。

**判据：用户按哪个键进来的？** 同一个功能键进入、再靠左右键翻的那几屏，
是**一页**的几个布局，不是几页。拆成多页有两个后果：翻页要走
`UI_SHOW_WINDOW` 整页重建（彩屏上是整帧重新合成，很贵）；
几屏共用的状态没地方放。

## 图层（`NewLayer`）= 一页恰好一个

两个样例工程合计 17 页，**每页都只有 1 个图层**，无一例外。

图层是页的唯一子节点，**整屏**。设备端 `struct layer` 自带 `draw_context`，
彩屏上它还对应一份 IMB 任务表和合成输出缓冲 ——
**它是绘制/合成的单位，不是"图层叠加"的设计元素**。

**不要一页建多个图层**（内存翻倍，而且两层的合成顺序不由你排）。
想要"叠一层上去"的效果，用**布局 + `invisible`**。

命名照 `<模式>_LAYER`：`BT_LAYER` `MUSIC_LAYER` `SYSTEM_LAYER`。
图层可以注册事件回调，但没有 `ui_layer_xxx()` API。

## 布局（`NewLayout`）= 两种用途

### 用途一：顶层布局 —— 主界面和弹层

图层下面直接挂的布局，靠 `invisible` 区分主次。样例工程的蓝牙页：

```
BT_LAYER                             整屏
├─ BT_LAYOUT           show          ← 主界面
├─ BT_VOL_LAYOUT       hide          ← 音量弹层
├─ BT_MENU_LAYOUT      hide          ← 菜单弹层
├─ BT_MENU_EQ_LAYOUT   hide          ← EQ 弹层
└─ BT_LAYOUT_CALL      hide          ← 来电/通话层
```

各页的顶层布局数（样例）：菜单 1、蓝牙 5、FM 3、时钟 5、音乐 6、
开机 1、关机 1、系统 9、PC 4、LINE-IN 4、录音 4。
**弹层多就是布局多，图层永远是 1 个。**

命名约定（应用代码按这个找控件）：

| 用途 | 命名 |
|---|---|
| 主界面 | `<模式>_LAYOUT` |
| 音量弹层 | `<模式>_VOL_LAYOUT` |
| 菜单弹层 | `<模式>_MENU_LAYOUT` |
| 其他弹层 | `<模式>_<用途>_LAYOUT` |

顶层布局**不一定要整屏**：样例工程屏是 240×240，而主布局是
`0,60 240×120`（界面内容在中间一条）。按设计稿来，
但同一页的主界面和弹层最好对齐，否则弹层弹出来位置会飘。

### ⚠ 弹层要排在主界面之后

按键分发规则是「**子元素从尾往前**，都不消费才轮到父节点自己」，
并且 `invisible` 的整棵子树**直接跳过**。

所以弹层只要满足两条，就自动获得"弹出时抢占按键"的效果：

1. 默认 `invisible = true`（json 里是把 `invisible` 项的 `default` 改成 `"true"`）
2. 在 `layout[]` 数组里**排在主界面布局之后**

不需要在主界面的 `onkey` 里写「如果菜单开着就不处理」。
**顺序决定行为，摆的时候就要想好。**

> 样例工程的系统页有几个弹层排在 `SYSTEM_LAYOUT` **之前**（`SYS_MSG_LAYOUT`
> `SYS_POWEROFF` `SYSTEM_UPDATE` `SYS_LANGUAGE`），那几个不享受这个自动优先，
> 得自己处理按键。新做界面不要学这一处。

绘制顺序和按键相反：**`layout[]` 靠后的画在上面**，
所以弹层排在后面同时满足"画在上面"和"先收到按键"，两件事是一致的。

### 把老工程的窄条布局改成整屏

从点阵屏时代移植过来的彩屏工程，经常是**整屏 240×240，但每个布局都是
`0,60 240×120`**（内容只占屏幕中间一条，其余是黑边）。样例工程 11 页
全部如此。想把某一页做成真正的整屏界面时：

```
改之前                              改之后
CLOCK_LAYER    0,0   240x240        CLOCK_LAYER    0,0 240x240
├ CLOCK_LAYOUT 0,60  240x120        ├ CLOCK_LAYOUT 0,0 240x240   ← 主界面整屏
├ CLOCK_VOL_LAYOUT   0,60 240x120   ├ CLOCK_VOL_LAYOUT   0,0 240x240  ← 弹层也要跟着改
└ CLOCK_MENU_LAYOUT  0,60 240x120   └ CLOCK_MENU_LAYOUT  0,0 240x240
```

**三件事必须一起做，漏一件就出问题**：

1. **主布局 rect 改成整屏** —— 这是你本来想做的。
2. **同图层的弹层全部跟着整屏化，并且各自填一块不透明底色**
   （`background_color` 设成 `#000000` 之类）。
   原来主界面和弹层一样大，弹层盖住主界面是天经地义的；主界面一变整屏，
   弹层还是中间那条的话，**弹出时两者叠在一起糊成一片**。
3. **弹层里直接子控件的 y 全部 +60。** 坐标相对父节点，父节点从 `y=60`
   挪到了 `y=0`，子控件要补回这 60 才能停在原来的屏幕位置。
   （主布局里的子控件同理 —— 除非你本来就要重排。）

第 2、3 条是最容易漏的，因为改完主布局看着一切正常，
只有弹出菜单/音量层的那一刻才露馅。

### 用途二：嵌套布局 —— 分组和定位

布局里可以再套布局，用来：

- 把几个控件当一组整体显示/隐藏（给这一组一个 ename，切它的 `invisible`）
- 定位：子控件坐标**相对父布局**，整组挪动只改父布局的 `rect`
- 列表条目：`listwidget[]` 里每一项就是一个布局

布局本身不画东西（除非设了背景色/背景图/边框），是纯容器。

## 列表（`VerticalList` / `HorizontalList` / `NewGrid`）

条目放在 `listwidget[]` 里，**每个条目是一个 `NewLayout`**，
条目内部再放图片、文字：

```
BT_MENU_LIST  (VerticalList, sizehw=16, 240x60 @ 0,30)
├─ listwidget[0]  NewLayout  240x16 @ 0,13    ← 第一行
│    ├─ ImageList  BT_MENU_LIST_EQ_PIC
│    └─ Text       BT_MENU_LIST_EQ_TEXT
└─ listwidget[1]  NewLayout  240x16 @ 0,29    ← 第二行
```

条目坐标相对列表，按 `sizehw` 累加；可以排到列表可视区之外，滚动时才露出来。
设备端垂直/水平/表格**都是 grid**（类型码 5），API 都是 `ui_grid_*`。

---

# 三点五、⚠ 复用一个既有 ename 之前，先查代码是怎么驱动它的

改版时很容易"把某个不用了的控件挪过来改改用"。**但 ename 没变，
原来那套代码还在驱动它。**

真实案例：`MUSIC_START` 原本是 240×60 的"开始播放"临时大图，
`music_player_disp_status()` 里有一句 `ui_hide(MUSIC_START)` ——
播放 200ms 后把它藏掉、让出歌词的位置。把它挪到底部当**常驻播放键**之后：
进模式能看到 → 一播放就消失 → 暂停又出现。界面上看像是控件坏了，
其实是老逻辑在正常工作。

所以复用前固定查一遍：

```sh
grep -rn "MUSIC_START" apps/          # 不要加 | head，见下
```

**要么确认没有代码引用，要么把那段老逻辑一起改掉。**
真想"换个位置的新控件"，起一个新 ename 更省事。

### ⚠ 查"有没有引用"这类存在性问题，不要加 `| head`

`| head` 会把后面的匹配截断。实战里就是这么误判的：
`grep -rn "MUSIC_START" ... | head` 只看到前几条，
`music_action.c` 里那条关键引用被截掉了，于是断言"没有代码引用它"，
害得多测了一轮。

**存在性判断要看全量**（或者用 `grep -c` 先看总数）；
`| head` 只适合"我知道有很多、只想看几个样本"的场景。

# 四、建一页的完整清单

1. 在 `pages[]` **末尾**追加一页（别往中间插，会改掉后面所有 `PAGE_n`）
2. 页的 `property` 写成裸 rect：`[{"rect":{"x":0,"y":0,"width":W,"height":H}}]`，
   W/H 和其它页一致
3. 页下建 **1 个**图层，`ename = <模式>_LAYER`，整屏，`color_format = OSD16`
4. 图层下建主界面布局 `<模式>_LAYOUT`，`invisible = false`
5. 需要弹层就继续追加顶层布局，`invisible = true`，**排在主界面之后**
6. 往布局里摆控件，需要代码操作的**都要起 ename**
7. `python tools/check_project.py` → `python tools/gen_ename.py --check`
8. 应用侧：新建 `<模式>_action.c`，`#define STYLE_NAME JL`，
   用 `REGISTER_UI_EVENT_HANDLER(id)` 挂回调（见 `app.md`）
9. `ui_style.h` 里加 `#define ID_WINDOW_<模式>  PAGE_n`
10. **把新 `.c` 加进 `build/genFileList.c`**（不是 `build/fileList.c`，见 `app.md`）。
    漏了这步的症状是**链接期** `undefined reference to <你的新函数>`，
    不是编译报错 —— 因为那个 `.c` 压根没被编译。
    只挂事件回调、没被别处调用的文件更隐蔽：**连报错都没有**，
    界面照画，就是一个事件都不响应。
11. 人工导出资源（见 `export.md`），编译烧录
