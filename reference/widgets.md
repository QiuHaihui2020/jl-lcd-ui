# 各控件：什么时候用 · 怎么摆 · 代码怎么调

属性字段的写法见 `project.md` 第 6 节，这里讲**选型、限制和用法**。
代码片段取自 `apps/soundbox/ui/lcd/STYLE_SOUNDBOX/` 的真实业务代码。

---

## 选型速查

| 要显示的东西 | 用 | 为什么 |
|---|---|---|
| 固定文案、菜单项名、状态词（"已连接"/"未连接"） | **Text** + 多条 `str` | 走多国语言表，切语言自动跟随 |
| 运行时才知道的字符串（歌名、设备名、歌词） | **Text** + `set_text` 系列 | |
| 状态图标（蓝牙连/断、播放/暂停） | **ImageList** 摆多张，切 index | 一个控件搞定一个状态机 |
| 单张静态图（logo、图标） | **ImageList** 只摆一张 | 没有单独的"图片"控件 |
| 整屏底图、永不变的装饰 | 布局/图层的 **`background_image`** | 不占控件、不占 ID |
| 电量 | **Battery** | 自带分档和充电图逻辑 |
| 时:分:秒、播放进度 | **Time** | 自带分隔符和补零 |
| 音量值、频道号、纯数字 | **Number** | 自带位数和对齐 |
| 进度条、音量条、频率条 | **slider / vslider** | 组合控件，一次插一棵子树 |
| 圆环进度、表盘、指南针 | **progressbar / watch / compass** | 彩屏专有组合控件 |
| 可滚动的菜单、文件列表、EQ 选项 | **VerticalList / HorizontalList** | 滚动高亮框架包了 |
| 一组要整体显示隐藏的东西 | **NewLayout** | 容器，不画东西 |

### 现成范例在哪一页

**排版前先去看一眼同类控件已有的写法**，比照着文档从零编快得多，
也不会漏掉 caption / property 这些讲究。下面是样例工程里的实例
（用 `tools/dump_tree.py <工程.json> -p <页号> -v` 打开看）：

| 控件 | 实例数 | 去哪看 |
|---|---|---|
| 布局 NewLayout | 144 | 页 0 `MENU_LAYOUT`、页 1 `BT_LAYOUT` |
| 图层 NewLayer | 11 | 页 1 `BT_LAYER` |
| 列表 Grid | 23 | 页 1 `BT_MENU_LIST`、页 0 `MENU_MAIN_LIST` |
| 图片 ImageList | 145 | 页 1 `BT_STATUS_PIC`（状态机切图） |
| 电池 Battery | 9 | 页 1 `BT_BAT` |
| 时间 Time | 17 | 页 1 `BT_MUSIC_CUR_TIME`、页 3 对时层那六个 `CLOCK_TIMER_*` |
| 文字 Text | 150 | 页 1 `BT_TEXT` |
| 数字 Number | 14 | 页 1 `BT_VOL_NUM`、页 2 `FM_CH` |
| **slider** | 3 | 页 3 `CLOCK_TEMP_BAR` / `slider_220`（**推荐，零件严格等宽左对齐**）<br>页 2 `FM_SLIDER` 零件宽度和本体不一致，**别抄零件 rect**（见 `project.md`） |
| **vslider** | 1 | 页 4 `MUSIC_FILE_SLIDER` |

⚠ 上表的页号是 `SmallColorTFT.json`（模式界面工程）。
**`BT_Watch.json` 里一个 slider / vslider 都没有** —— 去那边 grep 会一无所获，
别据此以为"这套组合控件没人用过"而改用 ImageList 拼进度条（资源大一个数量级）。

progressbar / multiprogressbar / watch / compass 两个工程都没有实例，
只能照控件库 `UITools/control/ex/*.json` 的模板来。

---

## 两个都能做的时候选哪个

选错了不会报错，只是后面很难受。

### 数字：Number 还是 Text？

**用 Number。** 音量、频道号、序号都是。Text 也能显示数字，
但你得自己转字符串、补零、对齐。Number 直接塞 `struct unumber`。

例外：数字和文字混在一句话里（"第 3 首/共 12 首"）才用 Text。

### 时:分:秒：Time 还是两个 Number？

**用 Time。** 播放进度也是。Time 自带分隔符和补零，
一次 `ui_time_update_by_id()` 全刷完。拿两个 Number 拼，
分隔符要额外摆一个控件，还得自己处理 `09` 这种补零。

### 一张固定的图：ImageList 还是背景图？

- **要代码控制显示/隐藏/换图** → ImageList（有 ename，能调 API）
- **纯装饰，永远不变**（整屏底图、分隔线、边框花纹）→ 布局的 `background_image`

彩屏上这条比点阵更值钱：整屏底图走背景图可以用 **JPEG**，
省下一大块 flash；做成 ImageList 就是一个控件加一个合成任务。

### 状态图标：一个 ImageList 摆多张，还是多个各摆一张？

**一个控件摆多张，切 index。** 蓝牙连/断、播放/暂停都是。
摆多个控件的话，切状态要"藏一个显一个"，两个都藏或都显的 bug 迟早出现；
而且每个控件都占一个合成任务。

### 电量：Battery 还是 ImageList 摆 5 张？

**用 Battery。** 它自带分档换算和充电态（`charge_image` 是独立一组图）。
用 ImageList 你得自己写 `percent → index`，还得自己做充电动画。

### 进度/音量条：slider 还是 ImageList 摆很多张？

**要用按键/触摸调节的用 slider**，传百分比就行。

**但纯显示的进度条（比如播放进度）建议用 ImageList 切帧** ——
因为 **slider 会吃掉方向键**（见下面 slider 一节），
在按键驱动的页面上放一个纯显示的进度条，会把上一首/下一首键一起吃掉。
ImageList 方案 1 个节点、不碰按键，代价是最多 30 档、没有滑块圆点。

### 变化的数值/文字：Text/Number 还是预渲染图集？

**先看字形够不够用，这一条决定一切。**

- **固定文案**走 `str.list` → 资源生成时离线渲染，
  字体和字号取**xls 里那个单元格自己的格式**（样例工程是宋体 12 号，
  不是 `ResBuilder.xml` 的 `<Fonts>` —— 那个改了没用，见下面 Text 一节）。
- **运行时字符串**走设备端字库。
- **Number 和 Time 始终是图片拼的**（`number.list` 里 10 张图），不受字库影响。

（两套机制的区别见下面 Text 一节，很重要。）

| 情况 | 选 |
|---|---|
| 配置的字体和设计稿一致、放得下，而且文案要多语言 | **Text**，一次调用的事，资源小一个数量级 |
| 设计稿用的是特殊字形/特殊字号，或界面**所有字符本来就是预渲染位图** | **ImageList 图集**，这是正确选型，不是偷懒 |
| 要加一条新文案但改不了 `.xls` | **只能走图集**（见 Text 一节的结论二） |

选了图集就要接受 **30 张上限**（见下）。

**⚠ 别想着"整串图集放不下，那就逐字符摆等宽 ImageList"。**
设计稿的字多半是比例间距的（`1` 和 `.` 比字母窄），
按等宽格子摆出来字距对不上，一眼看得出来。

### 多个条目：列表还是手摆几个布局？

- **条目固定且很少（2~3 个）、不滚动** → 手摆布局更简单，高亮自己控
- **会滚动、条目多、或条目数运行时才知道** → 用列表

界线是**要不要滚动**。一旦要滚动，自己实现滚动+高亮+翻页是纯粹的重复劳动。

### 一组东西整体显示隐藏：套一层布局还是逐个切？

**套一层布局，切布局的 `invisible`。** 逐个切会漏，新增控件时容易忘。
而且切布局只改一个 `invisible`，切 N 个控件是 N 次重绘。

### 想"叠一层上去"：新建图层还是新建布局？

**新建布局。** 图层一页只有一个（见 `authoring.md`）。
弹层 = 整屏布局 + `invisible=true` + 排在主界面之后。

---

## Text —— 文字

**什么时候用**：所有文字。

**摆法**

- `str` 是个**列表**，里面放多国语言表的条目 id（`m1` `m30` …），不是字面文字。
  一个 Text 挂多条，运行时切"显示第几条" —— 状态词（已连接/未连接）
  就是这么做的，一个控件两条，不用两个控件。
- **两项 `-name` 都叫 `color`**（文字颜色 / 高亮颜色），靠 `caption` 和顺序区分，
  别去重、别合并。彩屏这两项是真彩色，直接写 `#ffRRGGBB`。
  **顺序是固定的：第一个 = 平时的字色，第二个 = 选中时的字色。**
  依据：`struct ui_text_info` 里这两个字段是 `color`(偏移 32) 和
  `highlight_color`(偏移 36)，反编译 `ui_text.c.o` 能看到取哪个字段是由
  "当前是否高亮"选出来的（IR 里一个在 36 和 32 之间选的 `phi`）。
  **给列表做"选中项高亮"就是改第二个**，不用写代码。
  ⚠ 做 `-name` 去重时千万别把这两项合成一个 —— 合了之后高亮色被静默丢掉，
  界面上表现为"选中和没选中一个样"，而 `check_project` 不会报错。
  ⚠ **两项写成同一个值，等于没有高亮**，症状和被合并一模一样。
  本仓库约定是 **常态 `#ffa6b8d8` / 高亮 `#ffffffff`**（99 个 Text 都这样），
  照抄这一组就行。实测踩过：闹钟页 `ALM_SUN`~`ALM_SAT` 两项都写成 `#ffe6f1ff`，
  而那几个控件的 highlight 表示的是"这天重复开启"——**等于这个状态在界面上
  根本不可见**，不是"不好看"而是功能丢失。
  这条 `check_project` 报不了：json 看不出哪些 Text 会被代码 highlight，
  按"两份相同"硬报的话样例工程就有 47 条噪音（标题类 Text 本来就不需要高亮）。
  **给会被 highlight 的 Text 摆版时自己确认第二项。**
- `source`（数据源）一般保持默认。
- **`code` 决定这个控件能用哪组 API**（见下），默认 `strpic`。
- `str` 最多 100 条。

### ⚠⚠ 改页面底色时，必须同时扫一遍这一页所有 Text 的颜色

**Text 的文字颜色默认是黑的**（工程里两个 `color` 都是 `#ff000000`）。
页面底色本来是浅色，改成深色/黑色之后 → **黑字黑底，完全看不见**。

这不是个别控件的问题，是**成片的**。样例工程实测 119 个 Text 用黑字：

| 页 | 黑字 Text 数 |
|---|---|
| 7（系统设置） | **46** |
| 1（蓝牙） / 3（时钟） | 各 15 |
| 10（录音）/ 8（PC）/ 9（LINE-IN） | 13 / 12 / 12 |
| 2（FM） | 5 |

而且**弹层里的更容易漏**：主界面的黑字一眼看得见，弹层要按键才弹出来，
改完底色测主界面没问题，一按 MENU 整片全黑。

```sh
# 改底色前先数一遍这一页有多少黑字
python tools/dump_tree.py <工程.json> -p <页号> --props | grep -c "color='#ff000000'"
```

> 有一种情况不受影响：**整页文字全用图片做**（ImageList 图集）时，
> Text 控件本来就没几个。时钟页就是这样，所以改黑底时没暴露问题 ——
> 别因为一页没事就以为其它页也没事。

### ⚠ `code` 属性决定能调哪组 API，是排版时就定死的

不是"运行时想用哪个用哪个"。`ui_text.h` 本身就按 `code` 把 API 分成三段
（`/*** api of format 'strpic' ***/` 这种注释），设备端靠
`strcmp(code, ...)` 分派：

| `code` | 能调的 API | 文字从哪来 |
|---|---|---|
| `strpic`（工程默认） | `ui_text_show_index_by_id` / `set_index` / `set_combine_index` / `set_multi_text_index` | 多国语言表的**预渲染位图** |
| `text` | `ui_text_set_text_by_id` / `_textw_by_id` / `_textu_by_id` | 运行时字符串，走设备端**字库** |
| `ascii` | `ui_text_set_str` / `set_utf8_str` / `set_str_by_id` | 同上 |

**所以"这个控件显示固定文案还是运行时内容"必须在排版阶段就想好。**
摆成 `strpic` 却在代码里调 `ui_text_set_text_by_id()`，或者反过来，
都是不响应，而且不报错。

**代码怎么调**

```c
/* code = strpic：切到 str 列表里的第 index 条（跟随语言切换）*/
ui_text_show_index_by_id(BT_STATUS_TEXT, 1);   /* "已连接" */
ui_text_show_index_by_id(BT_STATUS_TEXT, 0);   /* "未连接" */

/* code = text：塞运行时才知道的内容 */
ui_text_set_text_by_id (id, str, len, FONT_DEFAULT);                    /* ANSI/GBK */
ui_text_set_textu_by_id(id, utf8, len, FONT_DEFAULT);                   /* UTF-8 */
ui_text_set_textw_by_id(id, wstr, len, FONT_ENDIAN_SMALL, FONT_DEFAULT);/* 宽字符 */

/* code = ascii */
ui_text_set_str_by_id  (id, "%s", str);
```

### ⚠⚠ 框架不拷贝字符串，只存指针

`ui_text.h` 里每个 set 函数的 `@param str` 都写着
**「字符串 buf 生命周期必须与控件一致」**。传进去的指针被控件一直拿着，
每次重绘都从那儿读 —— **传局部数组进去，函数一返回就是野指针**，
表现是花屏或乱码，而且发作时机随重绘时机漂移，极难查。

所以缓冲必须是**全局或静态**的。样例代码就是这么做的：

```c
/* music_action.c：歌名缓冲是全局数组，不是局部 */
u8 ui_music_file_name[128] = {0};

const char *ui_get_music_file_cur_name(struct music_player *hd, int *len, int *is_unicode)
{
    fget_name(hd->file, ui_music_file_name, sizeof(ui_music_file_name));
    ...
    return (const char *)ui_music_file_name;      /* 返回全局缓冲 */
}
```

`ui_text_set_combine_index()` 的 `store_buf` 参数注释说得更直白：
**「必须是全局或者静态，不能是局部 buf」**。

### `flags` 位（`font/font_all.h`）

| 宏 | 值 | 作用 |
|---|---|---|
| `FONT_SHOW_PIXEL` | 0x02 | 正常显示，`FONT_DEFAULT` 就是它 |
| `FONT_SHOW_MULTI_LINE` | 0x04 | **多行显示**（默认只显示一行） |
| `FONT_SHOW_SCROLL` | 0x08 | 超长滚动显示（歌名常用） |
| `FONT_HIGHLIGHT_SCROLL` | 0x10 | 高亮时才滚动 |
| `FONT_SHOW_SCROLL_RESET` | 0x40 | 滚动复位（换歌时用，从头滚） |
| `FONT_GET_WIDTH` | 0x01 | 只算宽度不画 |

编码/字节序另有 `FONT_ENCODE_ANSI/UNICODE/UTF8`、`FONT_ENDIAN_BIG/SMALL`。

```c
/* music_action.c：unicode 文件名 + 开滚动 */
ui_text_set_textw_by_id(LRC_TEXT_ID_NAME, file_name, len,
                        FONT_ENDIAN_SMALL, FONT_DEFAULT | FONT_SHOW_SCROLL);
```

⚠ 不带 `FONT_SHOW_SCROLL` 的长文字被**直接截断**，不带
`FONT_SHOW_MULTI_LINE` 的多行文本**只显示一行**，都不报错。

⚠ 滚动速度是**全局的，不是每个控件各自的**：
`text_set_strpic_scroll_interval()`（默认 250ms）和
`text_set_font_scroll_interval()`（默认 1000ms）分别管 strpic 和字库两条路。
`scroll_start_cnt` / `end_cnt` 的单位是**次数**，实际停留时间 = 次数 × 间隔。

### ⚠⚠ 固定文案和运行时文字是两套完全独立的机制

这决定了**哪些事 AI 能做、哪些必须人工**，排版前就要想清楚。

| | 固定文案（`str.list` 里的 `m*`） | 运行时字符串（`ui_text_set_*`） |
|---|---|---|
| 文字存在哪 | `多国语言_*.xls` | 代码里 / 运行时才知道 |
| 怎么变成像素 | **资源生成时离线渲染成 1bpp 位图**，打进 `JL.str` | 设备端字库实时渲染 |
| 字体/字号配在哪 | **xls 里那个单元格自己的字体和字号**（不是 `<Fonts>`，见 `platform.md` §6） | `F_ASCII.PIX` / `F_UNIC.PIX`，由 `字库工具/FontTool.exe` + `font.xml` 的 `<FontSize>` 生成 |
| 跟随语言切换 | 是 | 否 |

工程顶层的 `text_type: "1bpp"` / `texttype_type: "image"`、Text 的
`code: "strpic"`（string picture）说的就是第一条路。

**结论一：运行时不变的文字，一律加进 xls 用 strpic，别渲染成图。**
`.xls` 是二进制的，但**不等于只能人工改** —— 装了 Excel 的 Windows 机器可以用
COM 自动化加行，格式一点不丢（脚本、四个坑和验证办法见 `export.md` §6）。
所以"表里没有这句话"**不是**改用图片的理由，加一行就是了。改完重跑资源生成。

> 读 `.xls` 用 `pip install xlrd`：
> `xlrd.open_workbook(path, formatting_info=True)` 能读出每个单元格的
> 文案**和字体字号**（`b.font_list[b.xf_list[sheet.cell_xf_index(r,c)].font_index]`）。
> 查"m42 到底是哪句话""这条是几号字"不用开 Excel。
> ⚠ 它是**只读**的，写要走 COM；`xlwt`/`xlutils.copy` 会丢单元格格式，
> 而 strpic 的字号就在那里面。

⚠ **别拿近义条目将就。** 要"歌曲列表"而表里只有"播放列表"、要"恢复默认"
而表里是"出厂设定"时，加新条目，别凑合用 —— 凑合的结果是界面文案和设计稿
对不上，而且过一阵没人记得当初为什么不一样。

**结论一点五：改字号也要改 xls。**
固定文案的字号 = **那个单元格自己的字号**，不是 `ResBuilder.xml` 的 `<Fonts>`
（证据见 `platform.md` §6）。开 Excel 全选改字号，或者同样走 COM，
存成 `.xls`(BIFF8) 别存成 xlsx，然后重跑 step2 + `copy_file.bat`。

改完**先别烧录**，解析一下 `JL.str` 就知道成没成（方法见 `export.md` §6.5）——
实测踩过一次"工具预览已经变大、但 `JL.str` 一个字节没变"。

**结论二：预渲染成图片是退路，不是默认选项。**
它确实走得通（固定文案本来就是"离线渲染成位图"，自己渲染只是换了个渲染的人），
但丢三样东西：不跟随语言切换、**字号和同页其它 strpic 对不上**、改文案要重新出图。

> 实战里当场露馅：设置页五行，四行 strpic、一行因为"表里没有这句"拿图做。
> 图里的字居中、Text 是 `ALIGN_LEFT`，字号又是自己定的 16px，和宋体 24 对不上 ——
> 用户一眼看出那行歪了，而 json 上看不出问题，`check_project` 也不报。

**只有这几种情况才用图**：字库或表里没有那个字形；设计稿要的是特殊字形/特殊字号；
整块内容本来就是图（logo、艺术字）。

⚠ 这条**不管** Number / Time 的 `number.list` —— 那两个控件靠图片拼数字是
框架机制（见上面各自那一节），照用不误。

⚠ 工程 `config/` 目录下可能躺着一批 `m*.png`（`m43.png` 133×24 之类），
那是资源生成的中间产物，**工程 json 里一处都没引用**（`grep -c m43.png` = 0）。
不要把它们当成可以直接摆进界面的图片资源。

---

## ImageList —— 图片

**什么时候用**：任何要代码控制的图。名字叫 List 是因为它天生就是"一组图选一张"。

**摆法**

- `normal_image` / `highlight_image` 两个列表，分别是常态和高亮态。
- `image-type` 决定打包格式：不透明用 `RGB565`，要透明用 `ARGB8565`，
  大图用 `JPEG`（见 `platform.md`）。
- `play_mode` 不为 `PLAY_NONE` 时它自己按 `interval` 毫秒轮播 ——
  **做动画不用写代码**，这是彩屏工程里很常用的一招。
- `cent_x` / `cent_y` 是旋转中心（配合 `ui_rotate` 用）。
- ⚠ **`normal_image` 最多 30 张**（控件库里 `maxlength=30`）。
  对比：Battery 的 `image` 是 0 = 不限，Text 的 `str` 是 100，
  Number/Time 的 `number`/`delimiter` 是 10。

**⚠ 30 张上限是硬的**：超了在工程里只能列首帧占位，运行时切不动、等于一张死图，
而且不报错。超过 30 帧的图集要在设备端按索引从资源包取图（属于改固件的活），
**动手前就要算够不够**，别列到第 30 张才发现。

**代码怎么调**

```c
ui_pic_show_image_by_id(BT_STATUS_PIC, 1);   /* 切到第 1 张 */
ui_pic_set_hide_by_id(id, 1);                /* 单独藏这一张 */
int n = ui_pic_get_normal_image_number_by_id(id);
int m = ui_pic_get_highlgiht_image_number_by_id(id);   /* 注意这个拼写就是这样 */

/* 在控件自己的 ON_CHANGE_INIT 里设初值：它不触发重绘，安全 */
ui_pic_set_image_index(pic, 2);
```

---

## Battery —— 电池电量

**什么时候用**：电量图标。别用 ImageList 自己做。

**摆法**：`image` 按电量**从低到高**摆；`charge_image` 是充电时用的，可留空。

**代码怎么调**

```c
ui_battery_set_level_by_id(id, percent, incharge);  /* percent 0..100 */
ui_battery_level_change(percent, incharge);         /* 改所有电池控件 */

/* 回调里已经有控件指针，直接用带指针的版本 */
static int battery_onchange(void *ctr, enum element_change_event e, void *arg)
{
    struct ui_battery *battery = (struct ui_battery *)ctr;
    static u32 timer = 0;
    switch (e) {
    case ON_CHANGE_INIT:
        ui_battery_set_level(battery, get_vbat_percent(), 0);
        if (!timer) {
            /* 传的 priv 就是控件 ID，定时器回调里用 _by_id 版本刷 */
            timer = sys_timer_add((void *)battery->elm.id, battery_timer, 1000);
        }
        break;
    case ON_CHANGE_RELEASE:
        if (timer) { sys_timer_del(timer); timer = 0; }
        break;
    default: return false;
    }
    return false;
}
REGISTER_UI_EVENT_HANDLER(BT_BAT)
.onchange = battery_onchange,
 .ontouch = NULL,
};
```

---

## Time —— 时间

**什么时候用**：时:分:秒。**播放进度也用它**，不要用两个 Number 拼。

**摆法**：`format` 定格式，`number` 放 0-9 十张图，`delimiter` 放分隔符图，
`auto_cnt` 是否自动走秒。

### ⚠ `format` 区分大小写，年月日是大写

完整规则和分隔符的取图顺序见 `project.md`，这里只强调最容易错的一条：

```
Y 年(4位)   M 月(2位)   D 日(2位)      ← 大写
h 时(2位)   m 分(2位)   s 秒(2位)      ← 小写
其它字符 = 分隔符，按出现顺序取 delimiter.list[0]、[1]、[2]…
```

**日期写 `Y-M-D`，不是 `y-m-d`。** 小写 `m` 是分钟，小写 `y`/`d` 根本不是字段，
会被当成分隔符占位。这个错在工具里看不出来，上板才发现日期位置显示的是分钟。

现成的正确范例（都在样例工程里）：

| 想要 | `format` | 去哪看 |
|---|---|---|
| 完整年月日时分秒 | `Y/M/D h:m:s` | `BT_Watch` 页 4 `BaseForm_43`（⚠ 见下） |
| 只有日期 | `Y/M/D` | `BT_Watch` 页 2 `BaseForm_38` |
| 月-日 | `M-D` | `SmallColorTFT` 页 3 `CLOCK_TIME_YMD` |
| 单字段（时/分/秒各一个控件，好分别设字号） | `h` / `m` / `s` | `SmallColorTFT` 页 3 对时层 `CLOCK_TIMER_HOUR` 等六个 |

硬上限（越界就是静默截断）：`format` ≤ 15 字符、展开后 ≤ 18 个字形、
`delimiter` ≤ 10 张、`number` 正好 10 张。

⚠ **`BT_Watch` 页 4 那个 `Y/M/D h:m:s` 是范例也是反例**：format 写法本身是对的
（六字段两种分隔符，结构最完整），但它的 `delimiter` 列表**只配了 2 张图**，
而 format 里有 5 个分隔符位。按上面的规则，显示会在第 3 个分隔符处
**截断，后面的字段根本不画**。抄它的 format 可以，别抄它的配置 ——
`check_project.py` 会把这种情况报出来。

**代码怎么调**

```c
struct utime tm;        /* u16 year; u8 month, day, hour, min, sec; */
int sec = cur_ms / 1000;
tm.hour = sec / 3600;
tm.min  = sec / 60 % 60;
tm.sec  = sec % 60;
ui_time_update_by_id(BT_MUSIC_CUR_TIME, &tm);
```

⚠ **没配数字图片时**，整串**不走图片、直接交给 ASCII 字库**渲染 ——
所以"图片数字"和"字库数字"是靠有没有配图集切换的，不是靠别的开关。
（实现判的是 `number` 的第一个**资源索引**为 0 或 0xFFFF，不是数组长度，
效果上等价：没配图就没索引。）

### ⚠⚠ 双 css：做"选中高亮背景"的正路

**一个控件可以带两份 `element_css`：css[0] 普通态、css[1] 高亮态，
框架在选中时把【整份】换掉。** 这是做"选中行整行高亮"的正路，
而且**应用代码一行都不用写** —— 配好工程就自动生效。

支持的控件比想象的多。`ui_core_set_element_css` 的调用方（反编译 `ui_new.a`）：

| 目标文件 | 控件 |
|---|---|
| `layout.c` | **NewLayout** ← 整行高亮靠它 |
| `ui_pic.c` | ImageList |
| `ui_text.c` | Text |
| `ui_time.c` | Time |

以 `layout_onchange` 为例，`switch(event)` 里 `i32 8`(highlight) 的分支：

```llvm
%cmp.i = icmp ugt i8 %29, 1                ; css 份数 > 1 才切
%tobool.i = icmp ne i8* %arg, null         ; arg 非空=选中 / NULL=取消
%33 = getelementptr ... %struct.element_css1* %32, i32 %lnot.ext.i, i32 0
%call9.i = tail call ... @ui_core_set_element_css(%_layout, %34)   ; ← 整份换
```

换的是**整份 css**，`rect` / `align` / `border` 全在里面。所以两份
**该有的差异只在这两项外观字段**，其余必须逐字一致：

| 改哪项 | 效果 | 代价 |
|---|---|---|
| `background_color` | `fill_rect` 填一块底色 | **只能是直角** |
| `background_image` | 画一张背景图 | **可以圆角**；图的尺寸必须等于 rect(框架不缩放) |

样例工程时钟页那 8 个 Time 改的是 `background_color`（`#ff1e5fb4`）；
要圆角高亮行就改 `background_image`，挂一张和行等大的圆角图。

#### 实战：整行高亮怎么摆

给**行布局**（列表 `listwidget[]` 里的那个 NewLayout）加第二份 css 就行：

```
BT_MENU_LIST_EQ            NewLayout 224x30
  css[0] background_image = ""                      ← 常态
  css[1] background_image = "config/pic_mp3/ROW30_HL.png"   ← 选中，圆角蓝底
├ BT_MENU_LIST_EQ_PIC      左侧图标
├ BT_MENU_LIST_EQ_TEXT     文字
└ BT_UI_MENU_EQ_ARR        右侧箭头
```

⚠ **别再另摆一个"行底图片控件"**。那样每行多一个 ImageList、多一个 IMB
合成任务、多一次资源读取，而效果和双 css 完全一样。实战里一个 7 行的 EQ 列表
就此省掉 7 个控件。

#### ⚠ 分清两种"高亮"，它们的驱动方是不同的

| | 含义 | 谁负责 |
|---|---|---|
| **光标高亮** | 按键停在哪一行 | **框架**，双 css / `highlight_image` 全自动 |
| **持久状态** | 比如"当前生效的是哪个 EQ" | **代码**，`ui_pic_set_image_index(pic, 1)` 切第二帧 |

两者混淆会出事：把 EQ 图标的图集从 2 张删成 1 张之后，
`eq_pic_common_onchange` 里那句 `set_image_index(pic, 1)` 就切不动了
（`ui_pic_set_image_index` 内部有 `icmp sgt %num, %index` 的边界检查，
越界直接 return，不报错也不生效）。

想合二为一，就在列表的 `ON_CHANGE_INIT` 里把光标落到那个持久状态上：

```c
/* 进 EQ 菜单时光标直接停在当前生效的 EQ 上，于是"高亮行"就是"当前模式" */
case ON_CHANGE_INIT:
    ui_grid_set_item(grid, eq_mode_get_cur() % BT_EQ_MODE_NUM);
    break;
```

⚠ 这里必须用 `ui_grid_set_item()` 这个**宏**（`(grid)->hi_index = index`，
纯写字段），不能用 `ui_grid_set_hi_index()` 函数 —— `ON_CHANGE_INIT` 是建页面
那趟遍历里发的，此时碰别的控件(行布局)会重入绘制，见 SKILL.md 铁律 5。

#### ⚠ `ui-tools` 的属性面板只编辑第一份

在 GUI 里挪动一个带双 css 的控件，第二份 rect 不会跟着动 —— 排版改一次就错位
一次，而且编辑器预览里完全看不出来（预览只画普通态）。

症状：**平时位置正常，一选中就整个跳到别处**，高亮底色和数字一起跑偏。

本仓库实测：`SmallColorTFT` 时钟设置的 6 个 + 闹钟设置的 2 个 Time 控件，
两份 rect 从建页起就没对齐过（高亮那份 y 少 60），`9d17348` 做 240×240 适配时
只改了第一份，差距被拉大到整屏可见。

`check_project.py` 会把"两份除 `background_color`/`background_image` 外还有
差异"报成 **ERROR**。GUI 里挪过这类控件之后跑一次它。

---

## Number —— 数字

**什么时候用**：音量、频道号、序号这类纯数字。

**代码怎么调**

```c
struct unumber num;     /* u8 numbs; u8 type; u32 number[2]; u8 *num_str; */
num.type      = TYPE_NUM;
num.numbs     = 1;                       /* 几个数 */
num.number[0] = app_audio_get_volume(APP_AUDIO_CURRENT_STATE);
ui_number_update_by_id(BT_VOL_NUM, &num);
```

FM 频率这种带小数的，用两个数（`numbs = 2`）配合 `format` 里的小数点，
中间那个字符走 `delimiter.list`。**一个 format 最多两个 `%d`。**

### ⚠ 范围是 0..65535，而且显示不了负数

`struct unumber.number[]` 虽然声明成 `u32`，但 `ui_number_update()` 里有
`trunc i32 → i16` —— 控件内部存的是 **`u16`**。所以：

- **有效范围 0..65535**，传 70000 会回绕成 4464，不报错。
- **负数会变成大正数**：传 `-4` → `u16` 得 65532 → 再按 format 宽度取模，
  `%02d` 显示 `32`、`%04d` 显示 `5532`。**不是夹到 0，是回绕，更难发现。**
- 宽度是**取模截断不是撑宽**：`%02d` 传 123 显示 `23`。

**要显示负数，两条路**：

| 做法 | 代价 |
|---|---|
| 摆一张 `−` 号 ImageList，按正负切显示/隐藏，Number 只传绝对值 | 多一个控件；但**字形和图集统一**，推荐 |
| `unumber.type = TYPE_STRING` + `num_str = "-4"` | 走 ASCII 字库，字形和自己做的数字图集对不上 |

⚠ `format` 只认 `%d` / `%Nd` / `%0Nd`。写别的（`%x`、`%5.2f`…）设备端会
`printf("format error")` 然后直接 return，**整个控件什么都不显示**。

---

## slider / vslider —— 滑条

**什么时候用**：进度条、音量条、频率条。横向 `slider`，纵向 `vslider`。

**摆法**

- 是**组合控件**，从 `UITools/control/ex/slider.json` 整棵插进来：
  `right_pic`(未选中) / `left_pic`(已选中) / `slider_pic`(滑块) /
  `slider_text`(百分比，可选)。
- ⚠ **零件的 caption 一个字都不能改** —— 类型码由 caption 决定，
  改了就退化成普通图片，不报错，而且会打乱整页同类型控件的 ID 序号。
- ⚠ **零件的图走 `element_css.background_image`，不是 `normal_image`**；
  **`right_pic`/`left_pic` 要与 slider 本体等宽左对齐**，否则百分比刻度和槽对不上。
  完整规则和框架那句 `puts` 警告见 `project.md`。
- `step` 是步进。

**代码怎么调**

```c
/* 传的是百分比 0..100，不是原始值 —— 这行就是把频率换算成百分比 */
ui_slider_set_persent_by_id(FM_SLIDER, (fre - 8700) * 100 / (FREQ_MAX - 8700));
int p = slider_get_percent(slider);
slider_touch_slider_move(slider, e);     /* 触摸屏拖动 */
```

### ⚠⚠ slider 会吃掉方向键 —— 按键驱动的页面上放进度条必踩

**`slider` / `vslider` 自带 `onkey`，会消费 `UI_KEY_LEFT/UP/RIGHT/DOWN`
（37/38/39/40）去加减百分比，并返回 1 中止分发。** 所以页面上一放进度条，
这四个键就再也到不了布局的 `onkey`。

症状极具误导性：**只有部分键失灵**。因为 `UI_KEY_OK`(4) 不在它的 switch 里，
确认键能正常穿过去 —— 表现成"暂停键有反应，上一首下一首没反应"，
看着像按键驱动坏了，实际是进度条把键吃了。

反编译 `ui_slider.c.o` 的 `slider_onkey()`：

```c
if (handler->onkey) {                    /* 先调你注册的 onkey */
    if (handler->onkey(slider, e) != 0)
        return 1;                        /* ← 你返回非 0：压住默认行为，并消费掉 */
}
if (e->event >= 2) return 0;             /* 只处理特定的按键事件类型 */
switch (e->value) {
case 37: case 38:  百分比减;  return 1;   /* LEFT / UP */
case 39: case 40:  百分比加;  return 1;   /* RIGHT / DOWN */
default:                      return 0;   /* 其它键继续往上传 */
}
```

**两条解法：**

**A. 给 slider 注册自己的 `onkey` 拦截。**

```c
static int music_bar_onkey(void *ctr, struct element_key_event *e)
{
    switch (e->value) {
    case UI_KEY_UP:   app_send_message(APP_MSG_MUSIC_PREV, 0); return true;
    case UI_KEY_DOWN: app_send_message(APP_MSG_MUSIC_NEXT, 0); return true;
    case UI_KEY_LEFT:
    case UI_KEY_RIGHT: return true;   /* 本页用不到，挡住免得进度条的值被改跑偏 */
    default: return false;
    }
}
REGISTER_UI_EVENT_HANDLER(MUSIC_BAR)
.onkey = music_bar_onkey,
 .onchange = NULL, .ontouch = NULL,
};
```

⚠ **反直觉的地方：不能靠"返回 false 让键穿过去"。**
返回 0 时 slider 会接着执行自己那段，方向键照样被吃掉并返回 1。
**只有返回非 0 才压得住。**

**B. 纯显示的进度条干脆别用 slider**，改用 ImageList 切帧
（N 张不同长度的条，按百分比切图号）。1 个节点、完全不碰按键，
代价是最多 30 档、且没有滑块圆点。

> 选型：**要响应按键/触摸去调节的才用 slider；纯显示进度用 ImageList。**

---

## VerticalList / HorizontalList / NewGrid —— 列表

> 选中行要**整行高亮背景**：给行布局加第二份 `element_css`，
> 见上面「双 css：做"选中高亮背景"的正路」。框架自动切，不用写代码，
> 也不用另摆行底图片控件。

**什么时候用**：菜单、文件列表、EQ 选项这类可滚动的多条目。

**摆法**

- 条目放 `listwidget[]`，**每条是一个 NewLayout**，里面再放图标和文字。
- `scroll_mode`：`SCROLL` 连续滚 / `PAGE` 整页翻。
- `highlight_index` 默认高亮行。

### ⚠⚠ 行高和间距是**节点顶层**的 `sizehw` / `space`，不在 `property` 里

```json
{"-class":"NewList", "-type":"VerticalList", "caption":"垂直列表",
 "orientation":"Vertical",     ← 方向
 "sizehw": 24,                 ← 行高(水平列表时是列宽)
 "space": 8,                   ← 相邻条目的间距
 "listwidget":[ ... ],
 "property":[ ... ]}           ← 这里面只有 id/element_css/scroll_mode/highlight_index
```

**翻 `property[]` 是找不到它们的**，控件库 `control.json` 里列表控件的 `property`
也确实只有 `scroll_mode` 和 `highlight_index` 两项 —— 于是很容易得出
"列表没有行高参数"的错误结论，然后只去改条目的 rect。

**设备端只认条目自己的 rect，不读 `sizehw`/`space`。**
反编译 `ui_new.a` 的 `ui_grid_child_init()` 可见，滚动步进是**反推**出来的：

```c
y_interval = (max_top - min_top) - (row_num - 1) * 条目高;   // 遍历条目 rect 累出来的
if (y_interval != 0 && row_num > 1) y_interval /= (row_num - 1);
```

资源侧也印证了这点：`struct ui_grid_info`（`control.h`，`.sty` 里 grid 的描述）
只有 `page_mode` / `highlight_index` / `action` / `lua` / `info` 五项，
**根本没有 sizehw、space、interval 这些字段**，它们进不了资源。

**所以 `sizehw`/`space` 是 ui-tools 编辑器的排版参数**：它按这两个值生成条目 rect。
两边对不上的后果是**下次在 GUI 里碰一下这个列表，工具很可能按旧的 `sizehw`
把条目 rect 重排回去，把你改的行高冲掉**。

改行高的正确做法是**三处一起改**，改完自查它们自洽：

| 改什么 | 值 |
|---|---|
| 列表的 `sizehw` / `space` | 行高 / 间距 |
| 每个条目 `listwidget[i]` 的 rect | 高 = `sizehw`，y 按 `sizehw + space` 递进 |
| 条目内图标/文字的 rect | 在行高内垂直居中 |

实战规格（240×240、24 号字）：`sizehw=28` `space=4`，步距 32，
条目高 28、y = 0/32/64…，行内 24 高的图标 y=2。
行高给 28 而不是 24 是因为**少数条目用西文字体，同样 24 号下位图高 27**。

```sh
# 改完核对三者自洽
python - <<'EOF'
import jlui
for n,_,_ in jlui.page_nodes(page):
    if jlui.typecode(n) == 5:
        print(n['sizehw'], n['space'],
              [jlui.rect_of(k)['y'] for k in n['listwidget']])
EOF
```

**代码怎么调**

```c
ui_grid_highlight_item_by_id(id, item, true);
ui_grid_set_item_num(grid, n);              /* 动态条数 */
ui_grid_slide(grid, direction, steps);
ui_grid_set_slide_direction(grid, dir);
ui_grid_on_focus(grid);  ui_grid_lose_focus(grid);
```

⚠ **grid 和 slider 一样会消费方向键**（37/38/39/40）并返回 1 中止分发 ——
只不过它的默认行为（滚动列表）通常正是你想要的，所以不容易察觉。
需要让某个方向键做别的事时，同样是**在自己的 `onkey` 里返回非 0** 才压得住。
通则见 `app.md` 的按键分发一节。

⚠ **滚动和高亮不要自己算。** grid 的内置 `onkey` 结构是
「**先调本页注册的 `onkey`，返回真就直接结束；返回假才走自己那段**」，
所以列表的 `onkey` 里把键值改写成 `UI_KEY_UP` / `UI_KEY_DOWN` 再 `return false`，
滚动、高亮、翻页就全交给框架了：

```c
static int menu_list_onkey(void *ctrl, struct element_key_event *e)
{
    switch (e->value) {
    case KEY_NEXT: e->value = UI_KEY_DOWN; return false;  /* 交给 grid */
    case KEY_PREV: e->value = UI_KEY_UP;   return false;
    case KEY_OK:   do_something();         return true;   /* 自己消费 */
    }
    return false;
}
```

几个只有看过实现才知道的细节：

- **上下键会被就地改写成左右**（`UI_KEY_UP`(38)→`UI_KEY_LEFT`(37)、
  `UI_KEY_DOWN`(40)→`UI_KEY_RIGHT`(39)），横列表竖列表走的是同一段逻辑，
  框架内部不区分方向。所以改写成上下还是左右都行。
- **`highlight_index < 0` 时 grid 直接不滚，并放行按键。**
  "列表按了没反应"先查这个。
- **不认的键 grid 会继续上传**（return 0），不会被吃掉 ——
  所以列表所在的布局/页照样收得到 MODE、OK 这些键。
- **`ui_grid_set_item_num()` 不重绘**，改完要自己 `ui_redraw(id)`。
  而且 `item_num` 超过工程里摆的 `listwidget` 条数会 **`cpu_assert` 直接断言失败**，
  不是静默截断 —— 动态条数的上限由排版时摆了几条决定。

---

## 频谱/律动条这类动效怎么做

> ⚠ 这一节是**一次实现下来的经验**，不是从框架源码验证出来的通则。
> 控件选型那条（N 个 ImageList 而不是 N 个 slider）有明确依据；
> 信号处理那几条是那次调出来的效果，换个屏/换个柱子数要自己再调。

N 根跳动的柱子，**不要用 N 个 slider/vslider**（每个 4 个节点，光节点就 4N 个）。

**正确做法：N 个 ImageList 共用一组档位图，运行时切图号。**

- 档位图 `SPEC_00..SPEC_11` 表示 0~11 格，N 根柱子各是一个 ImageList，
  都挂这同一组图，**只占 N 个合成任务**。
- **倒影/渐变烘进图里**，柱高变化时自动跟随，不用额外画。

信号那一半有四个坑，每个都会让效果"看着不对但说不上哪不对"：

| 坑 | 后果 | 对策 |
|---|---|---|
| FFT 点数太少 | N=128 @44.1kHz 是 344Hz/点，**整个低音段全挤在直流那一格**，柱子对低音没反应 | 用 N=1024（43Hz/点） |
| 频段线性划分 | 低音全挤在第 1 根柱子，后面十几根几乎不动 | **按对数划分**，并随采样率缩放 |
| 档位线性映射 | 高频段全压成 0 档，而 0 档往往是空图 —— 表现成"只看得到几根柱子" | **档位也用对数刻度** |
| 不做频谱倾斜补偿 | 音乐天然 -5dB/倍频程，右半边永远够不到第 1 档 | 按频率加补偿增益 |

另外两条工程上的：

- **下落限速、上升不限速**（每周期最多掉 1 格）。不做这个包络，
  柱子会高频抖动，很难看。
- **刷新周期别太快**：16 个控件同刷，100ms 已经在压 IMB 了（见 `platform.md`）。

⚠ **FFT 不能在 UI 定时器里算** —— `JL_FFT` 是 CSFR 协处理器，内部忙等自旋，
会把整个 ui 任务拖死（`timer_no_response`）。计算放音频上下文，
UI 侧只负责把结果刷到控件上，见 `platform.md` 第 8.5 节。

## 彩屏专有的组合控件

这几个点阵屏那套没有，设备端实现在 `ui_new.a` 里，头文件都在
`interface/ui/jl_ui/ui/`。控件库模板在 `UITools/control/ex/`。

| 控件 | 类型码 | 零件 caption | API |
|---|---|---|---|
| progressbar | 20 | `progressbar_highlight` | `ui_progress_set_persent_by_id(id, p)` |
| multiprogressbar | 22 | `multiprogressbar_highlight` | `ui_progress_multi.h` |
| watch（表盘） | 24 | `watch_hour` / `watch_min` / `watch_sec` | `ui_watch.h`，指针按时间自转 |
| compass（指南针） | 38 | `compass_bkimg` / `compass_indicator` | `ui_compass.h` |

零件 caption 同样不能改。

---

## NewLayout —— 布局

**什么时候用**：容器。三种场合（见 `authoring.md`）：
主界面/弹层（整屏 + `invisible`）、分组、列表条目。

不画东西，除非设了背景色/背景图/边框。没有 `ui_layout_*` API，
但**可以注册 `onkey`** —— 弹层的按键就挂在它身上。

## NewLayer —— 图层

**一页恰好一个**，整屏。是绘制/合成缓冲的单位，不是设计元素。
想"叠一层"用布局 + `invisible`。没有 `ui_layer_*` API，可以注册回调。

---

## 不要用的

控件库 `control.json` 里有 `Button`(7)，设备端有 `ui_button.h`，
但两个样例工程都没用，且没有配套的资源属性 —— 要按钮效果就用
**ImageList + 高亮图**，触摸事件挂在它的 `ontouch` 上。

`typecodes` 里还能看到 `Camera`(11) `animation`(13) `player`(14)：
`Camera` 要摄像头模组，`animation`/`player` 设备端没实现。不要用。
需要动画用 **ImageList 的 `play_mode`**，需要转场用 `ui_effect.h`。
