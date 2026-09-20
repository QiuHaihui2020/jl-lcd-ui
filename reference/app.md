# 应用层怎么用这些控件

## 1. 控件和代码是怎么对上的

```
工程 json                          导出                  应用代码
property[id].ename = "BT_BAT"  ──────────►  ename.h → style_JL_new.h:
                                            #define BT_BAT 0X22400
                                                     │
                                            REGISTER_UI_EVENT_HANDLER(BT_BAT)
```

- **ID 是位域不是序号**，构成见 SKILL.md 铁律 1。可以用
  `tools/gen_ename.py` 提前算出来，不用等人工导出。
- ID 头（`style_JL_new.h` 或同类名字）**自动生成，不要手改** —— 每次导出都被覆盖。
  业务语义的别名写在 `ui_style.h`（手写、进版本库）：

```c
/* apps/soundbox/include/ui/ui_style.h */
#if (CONFIG_UI_STYLE == STYLE_JL_SOUNDBOX)
#define ID_WINDOW_MAIN     PAGE_0
#define ID_WINDOW_BT       PAGE_1
#define ID_WINDOW_FM       PAGE_2
...
#define ID_WINDOW_SPDIF    (-1)     /* 该工程没有这个页面，用 -1 表示无窗口 */
#endif
```

  `-1` 这个写法很实用：换一套界面时不用把用不到的模式代码全 `#if` 掉。

---

## 2. 事件注册（链接段收集）

> ⚠ 这一条和 jl-dot-ui（单色点阵）**相反**。彩屏这条链路的
> `interface/ui/jl_ui/ui/ui.ld` 里有段边界符号
> （`elm_event_handler_begin_JL` / `..._end_JL`），
> 所以链接段收集是**有效且唯一**的注册方式，不要去写什么显式注册表。

一页一个 `<模式>_action.c`，文件顶部：

```c
#include "ui/ui.h"
#include "ui/ui_api.h"
#include "ui/ui_style.h"

#if (TCFG_UI_ENABLE && (CONFIG_UI_STYLE == STYLE_JL_SOUNDBOX))

#define STYLE_NAME  JL          /* 决定段名 .elm_event_handler_JL，每个文件都要有 */
REGISTER_UI_STYLE(STYLE_NAME)   /* 整个 style 注册一次就够，放在其中一个文件里 */
```

然后每个要挂回调的控件写一段：

```c
static int bt_layout_onkey(void *ctrl, struct element_key_event *e) { ... }
static int bt_layout_onchange(void *ctrl, enum element_change_event e, void *arg) { ... }

REGISTER_UI_EVENT_HANDLER(BT_LAYOUT)
.onchange = bt_layout_onchange,
 .onkey   = bt_layout_onkey,
  .ontouch = NULL,
};
```

⚠ **那个宏不是一条完整语句** —— 它展开成
`static const struct element_event_handler element_event_handler_BT_LAYOUT sec(...) = { .id = BT_LAYOUT,`，
所以后面直接跟成员赋值、用 `};` 收尾。照抄现有文件的形状，别自己加分号或花括号。

三个口子：

```c
struct element_event_handler {
    int id;
    int (*ontouch)(void *, struct element_touch_event *);
    int (*onkey)(void *, struct element_key_event *);
    int (*onchange)(void *, enum element_change_event, void *);
};
```

返回值约定：**返回真 = 我消费了这个事件**，框架不再往下传；返回假 = 继续。

⚠ 新建的 `.c` 文件要加进编译。**漏加的后果分两种**：
只挂了事件回调的文件，段里没有这一项，界面照画、就是一个事件都不响应（静默）；
被别处调用的文件则是 `undefined reference`（编译期就炸，反而好查）。

### ⚠⚠ 加新源文件改的是 `build/genFileList.c`，不是 `build/fileList.c`

这两个文件名太像，改错了会浪费一整轮：

| 文件 | 生成的变量 | 是否生效 |
|---|---|---|
| `build/genFileList.c` | `c_SRC_FILES` | ✅ **真正决定编译什么** |
| `build/fileList.c` | `objs` | ❌ 全仓展开零命中，死变量 |

`build/Makefile.mk` 里是 `c_OBJS := $(c_SRC_FILES:%.c=%.c.o)`，**只认 `c_SRC_FILES`**。
只改 `fileList.c` 的话，编译能过、链接报 `undefined reference` ——
很容易误判成"要编译两次"而再浪费一轮。

### ⚠ 连带：只能从顶层 `make`，别直接 `make -f build/Makefile.mk`

两个生成器的输出目标在两处写得不一样，**`build/Makefile.mk` 里那两行是反的**：

```make
# 顶层 Makefile:208 —— 对的
    … genFileList.c -o build/fileList.mk       # 有用的 → 被 include 的文件

# build/Makefile.mk:367-368 —— 反的
    … genFileList.c -o build/fileList.dumy     # 有用的 → 一次性废弃文件
    … fileList.c    -o build/fileList.mk       # 死的   → 覆盖掉被 include 的文件
```

构建之所以没坏，是因为 `include` 发生在 **parse 期**、recipe 执行在 **build 期**：
顶层 make 每次先把 `fileList.mk` 写对，子 make parse 时读到的是对的，
**之后才被 `fileList.c` 的版本覆盖** —— 等于每次构建都在修好上一次的覆盖。

所以盘上残留的 `fileList.mk` 往往是**死变量那一版**
（实测：274 行 `objs`、0 行 `c_SRC_FILES`）。这时候直接
`make -f build/Makefile.mk`，parse 读到的追加列表是空的。

**始终从顶层 `make`。**

⚠ **它出问题时的症状是"全线崩"，不要拿它去解释"缺某一个文件的符号"。**
`c_SRC_FILES` 有两个来源：`build/Makefile.mk:2` 的静态列表（实测 116 个 `.c`）
\+ `include build/fileList.mk` 追加的（实测 475 个）。**action 文件全部在后者**
（静态列表里一个都没有）。所以这条真发作时会一次性掉 475 个文件、
炸出成千上万条 undefined reference；**只缺一个文件的符号，
与这个假设不相容** —— 那种情况先查下面这条。

配套两条，都踩过：

- **跨层调用的头文件要放在 include 路径上。** 页面目录
  （如 `apps/soundbox/ui/lcd/STYLE_SOUNDBOX`）**不在** `build/include_dir.txt` 里，
  `apps/soundbox/include` 在。把头文件放在 `.c` 旁边，别的层 include 就是
  `file not found`。
- **移动头文件后要删陈旧的 `.d`**，否则 make 报
  `No rule to make target '旧路径/xxx.h'`。

### 顶部那几行 `#pragma *_seg`

每个 action 文件开头都有：

```c
#ifdef SUPPORT_MS_EXTENSIONS
#pragma bss_seg(".bt_action.data.bss")
#pragma data_seg(".bt_action.data")
#pragma const_seg(".bt_action.text.const")
#pragma code_seg(".bt_action.text")
#endif
```

这是给链接脚本分段用的，**新建文件时照抄并把 `bt_action` 换成自己的文件名**。

---

## 3. 控件生命周期

事件枚举顺序（`ui_core.h`）：

```
ON_CHANGE_INIT_PROBE, INIT, TRY_OPEN_DC, FIRST_SHOW, SHOW_PROBE, SHOW,
SHOW_POST, HIDE, HIGHLIGHT, RELEASE_PROBE, RELEASE, ANIMATION_END,
SHOW_COMPLETED, UPDATE_ITEM
```

实际触发顺序和语义（下面这段绘制流程是从 `ui_new.a` 的 bitcode
反编译 `ui_core_show_rect()` 读出来的，不是猜的）：

### 创建：只发一次

```
ON_CHANGE_INIT          arg = NULL      控件结构已建好，还没画
```

grid 特殊：子条目初始化**之前**发的是 `ON_CHANGE_INIT_PROBE`。

### 显示：每次重画都走一遍

```
1. ON_CHANGE_SHOW_PROBE    arg = NULL     给控件调整内容的机会
2. （框架组 draw_context）
3. ON_CHANGE_SHOW          arg = &dc      ★ 返回 0 = 我自己画完了，后面全跳过
4. 框架 fill_rect 背景色 → 画背景图 → 画边框
5. ON_CHANGE_SHOW_POST     arg = &dc
6. ON_CHANGE_FIRST_SHOW    arg = &dc      仅当 elm->state != 2，发完置 2
```

子元素全画完后父元素再收一次 `ON_CHANGE_SHOW_COMPLETED`。
开绘制上下文时另有一记 `ON_CHANGE_TRY_OPEN_DC`（grid 用它改可视区）。

### 隐藏：不销毁

```
ON_CHANGE_HIDE             置 state=1、invisible=1
```

控件还在，数据还在。**再显示时不会重发 `INIT`，也不会重发 `FIRST_SHOW`**。

### 销毁

```
1. ON_CHANGE_RELEASE_PROBE   深度优先遍历整棵子树，一定会发
2. ON_CHANGE_RELEASE         引用计数减到 0 才发
```

---

### ⚠⚠ 头号大坑：绘制期回调里**不能**调 UI 更新 API

`SHOW_PROBE` / `SHOW` / `SHOW_POST` / `FIRST_SHOW` / `SHOW_COMPLETED`
都是**在绘制过程中**发的。在里面调 `ui_pic_show_image_by_id()` /
`ui_text_set_*` / `ui_number_update_by_id()` 会两头出事：

```
ui_pic_show_image_by_id()
  └ ui_pic_show_image()
      ├ ui_pic_set_image_index()
      │    └ platform_api->load_widget_info(...)   ← 覆盖那份唯一的 static 缓冲
      └ ui_core_redraw() / ui_core_show()
           └ __ui_core_show()                       ← 重入整套绘制递归
```

`load_widget_info()` 返回的是资源管理器里**唯一一份**
`static union ui_control_info` 的地址，每次调用整块覆盖。
外层遍历正读着它就被内层冲掉 → **整棵子树的遍历散架**。
症状是一整页只剩一两个控件，看着完全像资源坏了。

**正解：框架自带的 `ui_set_call()`**

```c
static int bt_status_check(int param) { ...这里随便调 ui_xxx_*... return 0; }

case ON_CHANGE_FIRST_SHOW:
    ui_set_call(bt_status_check, 0);    /* 推迟到本轮事件分发结束再执行 */
    break;
```

签名是 `int ui_set_call(int (*func)(int), int param)`，回调返回 `int`。

### `ui_set_call()` 和直接调，是两个方向都会错的选择题

`ui_set_call()` 依赖一个**只在控件 onchange 回调期间**才有效的上下文句柄，
用错地方两边都是**静默失效**：

| 你在哪 | 怎么刷界面 | 用错了会怎样 |
|---|---|---|
| 控件的 `onchange` 里（尤其绘制期那 5 个事件） | **`ui_set_call(cb, 0)`** | 直接调 → 重入绘制 + 冲掉 static 缓冲 → **整棵子树画不出来** |
| app 消息回调 / 定时器回调 / 按键处理 | **直接调 `ui_xxx_*`** | 用 `ui_set_call` → 句柄是空的，**调用被静默丢弃**，界面不刷新 |

两条都不报错，都是"代码看着对、就是没反应"。

### ⚠ `ON_CHANGE_INIT` 也在这条规则里，而且它最阴

上面那张表写的是"绘制期那 5 个事件"，但 **`ON_CHANGE_INIT` 同样不能调
`*_by_id()` 去刷别的控件**。INIT 是在建页面这趟遍历里发的，此时**兄弟控件
可能已经建好了** —— 对已建好的控件调 `ui_pic_show_image_by_id()` 会真的走
`ui_core_redraw()`，一样重入、一样冲掉那份唯一的 `static union ui_control_info`。

分界不是事件名，是**"碰不碰别的控件"**：

```c
case ON_CHANGE_INIT:
    ui_pic_set_image_index(pic, 1);          /* ✅ 改自己，只写字段，不重绘 */
    ui_battery_set_level(battery, p, 0);     /* ✅ 同上，拿的是 ctr 句柄 */
    ui_register_msg_handler(ID_WINDOW_BT, tbl);   /* ✅ 不碰控件 */
    timer = sys_timer_add(NULL, refresh, 120);    /* ✅ 不碰控件 */
    ui_pic_show_image_by_id(OTHER_CTRL, 0);  /* ❌ 跨控件刷新 → 整页画不出来 */
    break;
```

**为什么它能潜伏很久**：同一段代码在不同页上表现完全不同，取决于目标控件
在遍历顺序里排在本控件**之前还是之后**。

- 排在之后 → 调用时控件还不存在 → 框架打一条 `element is null` 警告后返回，
  **等于没执行**，页面完全正常。
- 排在之前 → 调用真的打进去 → **整页只剩零星几个控件**，看着完全像资源坏了。

实际案例：`ui_spectrum_start()` 里原本有个"把 16 根柱子先清成 0 档"的循环。
它在音乐页跑了很久没事（16 根柱子都排在 `MUSIC_LAYOUT` 之后，16 条
`element is null` 警告被当成无害噪声），照搬到蓝牙页就变成**整页只显示歌名**。

> **推论：`element is null` 警告不是噪声，是"这次调用被吞了"的回执。**
> 看到它先问一句"我是不是在绘制期跨控件刷新了"，别当成无害的时序抖动。

### 那"控件 A 的初值要跟着控件 B 的状态"怎么办：让 A 自己去读 B

典型场景：列表标题栏右边挂一个"当前项/总项数"的计数器，进页面就得显示对。
很自然会写成"在**列表**的 `ON_CHANGE_INIT` 里 `ui_number_update_by_id(计数器)`"
—— 那就是上面这条规则，**两个方向都是坑，调顺序没用**：

| 计数器在 `layout[]` 里的位置 | 结果 |
|---|---|
| 排在列表**后面** | 控件还没建出来，`by_id` 返回 `-22` 静默丢弃，屏上留着 `0/0` |
| 排在列表**前面** | 调用真的打进去，绘制期重入，照样刷不上（严重时整页只剩零星几个控件）|

**正解是掉个头：谁的初值，谁自己刷。** 分界从来不是事件名，是"碰不碰别的控件"：

```c
/* 挂在【计数器控件】上，不是挂在列表上 */
#define DEFINE_LIST_COUNT_ONCHANGE(fn, list_id, total)                    \
    static int fn(void *ctr, enum element_change_event e, void *arg)      \
    {                                                                     \
        struct element *_lst;                                             \
        struct unumber _num;                                              \
                                                                          \
        if (e != ON_CHANGE_INIT) {                                        \
            return FALSE;                                                 \
        }                                                                 \
        _lst = ui_core_get_element_by_id(list_id);   /* ✅ 只查指针 */    \
        _num.type = TYPE_NUM;                                             \
        _num.numbs = 2;                                                   \
        _num.number[0] = _lst                        /* ✅ 只读字段 */    \
                         ? (((struct ui_grid *)_lst)->hi_index + 1) : 1;  \
        _num.number[1] = total;                                           \
        ui_number_update((struct ui_number *)ctr, &_num);  /* ✅ 改自己 */ \
        return FALSE;                                                     \
    }
```

三个操作都安全：`ui_core_get_element_by_id()` 只是查指针，读 `hi_index`
只是读字段，`ui_number_update()` 拿的是**自己的 `ctr` 句柄**（不是 `_by_id`
版本），只写字段不重绘。

⚠ 这时候顺序**反过来**要求：**A 要排在 B 之后**。A 的 INIT 里读 B 的状态，
得等 B 自己的 `onchange` 先跑完（比如列表在它的 INIT 里 `ui_grid_set_item()`
把光标落到当前生效项上），A 才读得到落好位的值。

> 一句话：**绘制期不准写别人，但可以读别人**。要读，就排在别人后面。

### 写可复用 UI 模块时的硬约束

把某个功能（律动条、进度条、状态图标组）抽成模块给多个页面调用时，
模块的 `xxx_start()` / `xxx_stop()` **一定会被人放进 `ON_CHANGE_INIT` /
`ON_CHANGE_RELEASE`**（那是唯一合理的挂载点）。所以：

> **模块的 start/stop 里不准碰控件**，只做挂定时器、开数据源、清自己的缓存。
> 控件初值交给定时器第一拍去刷，最多晚一个周期。

模块内部真正刷屏的那个函数跑在定时器回调里，那里是安全的，而且按上面那张表
**必须直接调 `ui_xxx_*`、不能用 `ui_set_call()`**。
`bt_action.c` 里两种写法都有，并且把理由注释出来了：

```c
/* 在 onchange 里：推迟 */
case ON_CHANGE_FIRST_SHOW:
    ui_set_call(vol_init, 0);
    break;

/* 在消息回调里：必须直接调 */
static int ui_music_vol_handler(const char *type, u32 arg)
{
    /* 这里必须直接调用，不能用 ui_set_call()：它内部依赖一个只在控件
     * onchange 回调里有效的上下文句柄；在本消息回调里那个句柄是空的，
     * 调用会被静默丢弃，表现为长按音量键时数字不刷新。 */
    vol_init(0);
```

### 弹层/子屏反复显示：用 `SHOW_POST`，不是 `FIRST_SHOW`

`FIRST_SHOW` **一辈子只发一次**（靠 `elm->state != 2` 判断）。
弹层被收起后再弹出、翻页切回某一屏，都不会再发 —— 数据会停在上次的值上。

```c
case ON_CHANGE_SHOW_POST:
    /* 每次显示都重新读一次当前音量：FIRST_SHOW 只在第一次显示时触发，
     * 音量界面被超时收起后再次弹出不会再走那里，数字会停在上一次的值上。 */
    ui_set_call(vol_init, 0);
    break;
```

**一次性的初始化放 `FIRST_SHOW`，每次显示都要刷的放 `SHOW_POST`**，两者都用 `ui_set_call()`。

⚠ 不要为了解决"隐藏的屏不会重发 FIRST_SHOW"，就在**某一屏的回调里替所有屏**
刷数据 —— 那等于在一次绘制里触发十几次重入。每屏管自己的 `SHOW_POST`。

### 另外四个容易踩的点

**一、`ON_CHANGE_SHOW` 返回 0 会跳过后面全部**，包括背景、边框、
`SHOW_POST` 和 `FIRST_SHOW`。自绘控件（grid/text）就是靠返回 0 接管绘制的，
它们**收不到 `FIRST_SHOW`**。

**二、`SHOW_PROBE` / `SHOW` / `SHOW_POST` 每次重画都发。**
不要在里面申请资源、起定时器、做重计算。
"只做一次"的事放 `INIT`（建控件时）或 `FIRST_SHOW`（首次显示时）。

**三、隐藏 ≠ 销毁。** 弹层反复弹出收起走的是 `HIDE`/`SHOW`，不会重新 `INIT`。

**四、停定时器放哪。** `RELEASE_PROBE` 一定会发（整棵子树深度优先），
`RELEASE` 要等引用计数归零。顶层控件两者都会到，样例代码放在 `RELEASE`；
**拿不准就放 `RELEASE_PROBE`。**

还有一条和时序无关但同样致命：定时器回调是**消息式投递**的，
`sys_timer_del()` 之后仍可能有一拍已经投出去在路上。
回调里必须先判页面私有状态是否已置空再用：

```c
static void music_timer(void *ptr)
{
    if (!__this) { return; }      /* 页面已释放，这一拍是路上的残留 */
    ...
}
```

### 实际写页面用得最多的三个

| 时机 | 干什么 |
|---|---|
| `ON_CHANGE_INIT` | 申请页面私有状态、`ui_register_msg_handler()`、起刷新定时器 |
| `ON_CHANGE_FIRST_SHOW` | `ui_set_call()` 拉一次当前数据刷到界面 |
| `ON_CHANGE_RELEASE` | 删定时器、释放私有状态 |

### 推荐范式：缓存置脏 + 定时器统一刷屏

数据从**任意来源**（网络、串口、协议栈回调、别的线程）随时进来的页面，
最省心的写法不是"来了就刷"，而是**只写缓存并置脏，刷屏统一放在页面的定时器里**。
这样从哪儿调进来都不会撞上绘制过程，`ui_set_call()` 那个选择题也就不存在了：

```c
struct clock_weather_info {
    ...
    u8 is_dirty;    /* 置位后由 500ms 定时器刷到界面上 */
};
static struct clock_weather_info s_weather = { ..., .is_dirty = 1 };

/* 对外的数据入口：任意线程都能调，只写缓存 */
void clock_ui_set_weather(const struct clock_weather_info *info)
{
    if (!info) { return; }
    s_weather = *info;
    s_weather.is_dirty = 1;      /* 不在这里碰任何 ui_xxx API */
}

/* 页面的 500ms 定时器：唯一刷屏的地方 */
static void timer_add_update(void *priv)
{
    ...
    if (ui_get_disp_status_by_id(CLOCK_LAYOUT) <= 0) {
        /* 注意：这个判断只在弹层真的 ui_hide 了主布局时才成立，
         * 同页兄弟布局盖上来是查不出来的，见下面那条 ⚠ */
        s_weather.is_dirty = 1;
        s_week_last = 0xFF;
    } else if (s_weather.is_dirty) {
        s_weather.is_dirty = 0;
        clock_weather_show();    /* 定时器回调里是直接调，不用 ui_set_call */
    }
}
```

三个要点（**每一条都能独立从框架行为推出来，不依赖这个页面的具体业务**）：

1. **被盖住时不刷，只标脏。** 回来时要保证整体重刷一次 —— 上面那个 `else if` 就是干这个的。
   但**怎么判断"被盖住"要看清楚**，见下面那条 ⚠。
2. **"值没变就不刷"另外用一个变量记**（例子里的 `s_week_last`）。
   依据：`ui_pic_show_image_by_id()` 内部会 `ui_core_redraw()`，
   **每次调用都触发重绘**，不判重就是每 500ms 重画一次，白白占合成任务和功耗。
3. **定时器回调里直接调 `ui_xxx_*`，不要用 `ui_set_call()`。**
   依据：这就是铁律 5 那张表的下半行 —— `ui_set_call()` 的上下文句柄
   只在控件 onchange 回调期间有效，定时器里是空的，调用会被静默丢弃。

这三条是通则。至于"缓存结构体长什么样""定时器 500ms"这些，是那一页的具体做法，
照搬时按自己的刷新需求定。

### ⚠⚠ `ui_get_disp_status_by_id()` 判不出"被同页弹层盖住"

**这是本 skill 以前教错过的地方，实测踩过，代价是一整轮烧板。**

彩屏工程的弹层是"同一页里另一个 `invisible` 的布局"（铁律 7）。`ui_show(弹层)`
**不会去 hide 主布局** —— 主布局还在显示中，只是被压在下面。所以：

```c
/* ✗ 永远不成立：弹层盖着主界面时，主布局的 disp 状态仍然是"显示" */
if (ui_get_disp_status_by_id(XXX_LAYOUT) <= 0) { return; }
```

它只在**弹层显式 hide 了主布局**时才有效。这种用法确实存在（例如蓝牙通话层
`BT_LAYOUT_CALL` 是 `ui_hide(BT_LAYOUT)` 之后再显示自己的），但那是少数。
**默认情况下你查不出覆盖，框架也没有"这个控件当前是否被别人压着"的接口。**

#### 为什么必须判出来：被盖住的控件，刷屏不但没用，还更贵

框架**不会**因为控件被盖住就省掉这次 blit。它照样重画该控件那块区域，
然后还得把压在上面的弹层重新合成一遍 —— 单层直写变成双层合成。
所以"被盖住还按拍刷"是**比平时更重**的浪费，实测表现为弹窗一出来
`timer_no_response: ui` 立刻刷屏。

#### 正确做法：让弹层自己说

唯一可靠的信号源是弹层自己的 `ON_CHANGE_SHOW` / `ON_CHANGE_HIDE`
（**不能用 INIT/RELEASE，见下一节**）：

```c
/* 页面侧维护"谁盖着我"，按 ID 记账而不是简单计数 */
#define PAGE_COVER_MAX  5           /* 菜单/EQ/循环/文件/音量 */
static int s_cover_id[PAGE_COVER_MAX];
static u8  s_covers;

static void page_cover_enter(int id)
{
    u8 i;
    for (i = 0; i < s_covers; i++) {
        if (s_cover_id[i] == id) { return; }        /* 幂等 */
    }
    if (s_covers < PAGE_COVER_MAX) { s_cover_id[s_covers++] = id; }
}

static void page_cover_exit(int id)
{
    u8 i;
    for (i = 0; i < s_covers; i++) {
        if (s_cover_id[i] == id) {
            s_cover_id[i] = s_cover_id[--s_covers];  /* 拿末尾填空位 */
            break;
        }
    }
}

/* 每个会盖住主界面的弹层都注册这个 */
static int page_popup_onchange(void *ctr, enum element_change_event e, void *arg)
{
    struct layout *layout = (struct layout *)ctr;
    if (e == ON_CHANGE_SHOW) {
        page_cover_enter(layout->elm.id);
    } else if (e == ON_CHANGE_HIDE) {
        page_cover_exit(layout->elm.id);
    }
    return FALSE;       /* 别把弹层自己的绘制吞掉 */
}

/* 定时器里 */
if (s_covers) { return; }
```

两个细节值得照抄：

- **按 ID 记账，不要用简单计数。** 某个弹层漏发一次配对事件时，只会影响它
  自己，不会把整页的刷新永久关掉。计数一旦不配平就是"界面再也不动了"，
  是用户一眼能看见、又极难复现的故障。同一 ID 重复 `enter` 幂等，所以
  **弹层套弹层**（菜单里再开 EQ，两个都在显示）也是对的。
- **进页面时清一次**（在主布局的 `ON_CHANGE_INIT` 或 window 的
  `ON_CHANGE_INIT` 里 `s_covers = 0`）。上次退出页面时如果有弹层没走到
  `HIDE`，这里能自愈。

#### 恢复时要不要补刷？分两种

- **图片类控件（`ui_pic_show_image_by_id`）要补。** 自己维护的"上次刷了哪一档"
  缓存（要点 2 的 `s_week_last`）必须在恢复时清掉，否则"值没变就不刷"会把
  恢复后的第一拍挡掉，留一片空白。
- **文字类控件（`ui_text_set_*`）不用补。** 反编译 `ui_new.a` 可以看到
  `ui_text_set_wstr()` 只 `store` 字符串指针、**不拷贝内容**，元素一直握着
  那个指针；弹层收起时 `ui_core_hide()` 会走 `ui_core_redraw()`，用这个指针
  把文字重新渲染出来。所以遮挡期间直接跳过更新是安全的。
  （反过来说：那块内存在控件还显示着的时候不能复用，见 `widgets.md`。）

---

### ⚠⚠ 弹层的显示/隐藏配对，只能用 `ON_CHANGE_SHOW` / `ON_CHANGE_HIDE`

`ON_CHANGE_INIT` 只在 `layout_init()` 里发**一次**，`ON_CHANGE_RELEASE` 只在
`layout_release()` 里发 —— 而**弹层反复弹出收起并不销毁控件**（见上面"隐藏：不销毁"）。
反编译 `ui_new.a` 可以确认这四个事件各自的发出者：

| 事件 | 发出者 | 时机 |
|---|---|---|
| `ON_CHANGE_SHOW` | `ui_core_show_rect()` | **每次**显示 |
| `ON_CHANGE_HIDE` | `ui_core_hide()` | **每次**隐藏 |
| `ON_CHANGE_INIT` | `layout_init()` | 控件创建，仅一次 |
| `ON_CHANGE_RELEASE` | `layout_release()` | 控件销毁（一般是退出页面） |

所以用 INIT/RELEASE 做"弹出时暂停 / 收起时恢复"的结果是：

> 第一次弹窗暂停之后，**永远不会恢复**（直到退出页面）。

而且这个 bug 很难从现象上认出来 —— 第一次弹窗的行为完全正确，只有第二次
才看得出不对。**布局是懒创建的**，`ON_CHANGE_INIT` 是在第一次 `ui_show`
时才发，所以连"进页面就坏掉"这种明显症状都没有。

注意这条和铁律 5 不矛盾：铁律 5 说的是**在这些回调里不能碰别的控件**，
这里做的是改自己模块的标志位，不碰任何 `ui_*` API。

---

## 4. 窗口、弹层、跨模块消息

### 窗口（页）

```c
UI_SHOW_WINDOW(ID_WINDOW_BT);     /* = ui_show_main(id) */
UI_HIDE_WINDOW(ID_WINDOW_BT);     /* = ui_hide_main(id) */
UI_HIDE_CURR_WINDOW();
int cur = UI_GET_WINDOW_ID();     /* = ui_get_current_window_id() */
```

这几个宏在 `ui_api.h` 里按 `CONFIG_UI_STYLE` 分流（led7 / 彩屏 / 去框架各一套），
**页面代码一律用宏**，别直接调 `ui_show_main()`，换显示方案时才不用改业务代码。

### 弹层（同一页里的布局）

```c
ui_show(BT_MENU_LAYOUT);                        /* 显示 */
ui_hide(BT_MENU_LAYOUT);                        /* 隐藏 */
int st = ui_get_disp_status_by_id(BT_MENU_LAYOUT);
ui_redraw(id);                                  /* 强制重画 */
```

### ⚠ `ui_get_disp_status_by_id()` 的返回值，别信头文件注释

| 返回 | 含义 |
|---|---|
| `1` | 显示中 |
| `0` | 隐藏（`invisible` 置位） |
| `-14` | **控件不存在**（`get_element_by_id` 返回 NULL） |

`interface/ui/jl_ui/ui/ui.h` 里那行 `@return false 显示，true 隐藏`
**和实现是反的**（反编译 `ui_core_get_disp_status_by_id()` 确认：
`return !css.invisible`，找不到控件返回 `-EFAULT`）。照注释写会写反。

所以现有业务代码的写法是对的：

```c
if (ui_get_disp_status_by_id(id) <= 0) { ... }   /* 隐藏 或 不存在 → 当没显示 */
if (ui_get_disp_status_by_id(id) == true) { ... } /* 碰巧对(1 == true)，别学这种写法 */
```

判断"当前是否显示"统一用 `> 0`，把"控件不存在"和"隐藏"一起当成没显示 ——
这也是换界面工程后代码不会崩的原因（控件没了返回 -14，不是野指针）。

按键分发是**子元素从尾往前**，`invisible` 的整棵子树直接跳过，
所以弹层排在主布局之后就自动抢占按键，不用写"菜单开着就不处理"的判断
（见 `authoring.md`）。

⚠ 但**互斥关系还是要自己管**。样例代码的做法是进新弹层前逐个查旧的：

```c
if (ui_get_disp_status_by_id(BT_MENU_LAYOUT) == true) {
    ui_hide(BT_MENU_LAYOUT);
} else if (ui_get_disp_status_by_id(BT_VOL_LAYOUT) == true) {
    ui_hide(BT_VOL_LAYOUT);
}
ui_show(BT_LAYOUT_CALL);
```

### 跨模块消息：`UI_MSG_POST` + `uimsg_handl`

业务侧（蓝牙协议栈、播放器）要刷界面时，不直接调 UI API，而是发消息：

```c
/* 业务侧 */
UI_MSG_POST("music_start", "show_lyric", have_lrc);   /* = ui_server_msg_post */

/* 页面侧：一张表 + 在 ON_CHANGE_INIT 里注册 */
static int music_start(const char *type, u32 arg)
{
    if (type && !strcmp(type, "dev")) {
        ui_pic_show_image_by_id(MUSIC_DEV, 1);     /* 消息回调里直接调，见上文 */
        return 0;
    }
    ...
    return 0;
}

static const struct uimsg_handl ui_msg_handler[] = {
    { "music_start", music_start },
    { NULL, NULL },                 /* 必须以此结尾！ */
};

case ON_CHANGE_INIT:
    ui_register_msg_handler(ID_WINDOW_MUSIC, ui_msg_handler);
    break;
```

⚠ 表**必须以 `{NULL, NULL}` 结尾**，漏了就是越界遍历。
消息名和 `type` 都是字符串比较，写错了静默不响应。

### 按键分发模型

反编译 `ui_core.c.o` 的 `__ui_core_onkey()`，分发规则是确定的：

```c
for (p = elm->child.prev; p != &elm->child; p = p->prev) {  /* ① 子元素从尾往前 */
    if (p->flags & 4) continue;                             /* ② 该位置位的子树整棵跳过 */
    if (__ui_core_onkey(p, e) != 0) return 非0;             /* ③ 谁消费就停止分发 */
}
/* ④ 所有子元素都没消费，才轮到本元素自己的 handler */
```

这四条解释了 skill 里好几处行为：

- ① 是**弹层排在主布局之后就能抢占按键**的原因（`authoring.md`）。
- ② 那个位就是 `element_css.invisible`：IR 里被测字节落在 element 基址 +32，
  正是 `struct element_css` 的起点，而 css 第一个字节是
  `align:2` / **`invisible:1`（bit 2）** / `z_order:5`。
  而且是 `continue` —— **连递归都不进，整棵子树一起跳过**。
- ③ 意味着**任何一个子控件返回非 0，后面的兄弟和父节点都收不到这个键**。
- ④ 所以布局/页面的 `onkey` 是**兜底**，不是优先。

由 ② 可以合并出一条完整规则，两半分别在别处验证过：

> **`invisible` 的整棵子树，既不绘制（不产生 IMB 合成任务），也不参与按键分发。**

绘制那半见 `platform.md` 的 `RING_MAX_TASK` 一节。

### ⚠ 通则：组合控件会消费方向键

由 ③ 推出的一个高频坑：**`slider` / `vslider` / `grid` 都自带 `onkey`，
都会消费 `UI_KEY_LEFT/UP/RIGHT/DOWN`(37/38/39/40) 并返回 1 中止分发。**
在按键驱动的页面上放这几种控件，方向键就到不了布局的 `onkey` 了。

它们的 `onkey` 结构是一样的（反编译 `slider_onkey` / `grid_onkey` 对比确认）：

```c
if (handler->onkey && handler->onkey(ctrl, e) != 0)
    return 1;                 /* 你注册的 onkey 返回非 0 → 压住默认行为 */
switch (e->value) {
case 37: case 38: case 39: case 40:  做自己的事;  return 1;   /* 方向键被吃掉 */
default:                             return 0;                /* 其它键正常穿透 */
}
```

所以：

- **症状是"部分键失灵"**：`UI_KEY_OK`(4) 走 default 返回 0，确认键正常；
  只有方向键不响应。看着像按键驱动坏了。
- **压住默认行为要返回非 0**，返回 0 是压不住的（见 `widgets.md` 的 slider 一节）。
- 菜单页放 `grid` 是同一个坑，而且比 slider 更常见 —— 只不过 grid 的默认行为
  （滚动列表）通常正是你想要的，所以不容易察觉它"吃"了键。

### 按键

`onkey` 收到的是框架归一化后的键值（`ui.h`）：

```
UI_KEY_POWER_START 0   UI_KEY_POWER 1    UI_KEY_PREV 2       UI_KEY_NEXT 3
UI_KEY_OK 4            UI_KEY_CANCLE 5   UI_KEY_MENU 6       UI_KEY_MODE 7
UI_KEY_PHOTO 8         UI_KEY_ENC 9      UI_KEY_VOLUME_DEC 10 UI_KEY_VOLUME_INC 11
UI_KEY_PHONE 12        UI_KEY_LEFT 37    UI_KEY_UP 38        UI_KEY_RIGHT 39
UI_KEY_DOWN 40
```

页面代码**不要直接干业务**，发 app 消息让业务层做：

```c
static int bt_layout_onkey(void *ctrl, struct element_key_event *e)
{
    switch (e->value) {
    case UI_KEY_MENU:
        if (ui_get_disp_status_by_id(BT_MENU_LAYOUT) <= 0) { ui_show(BT_MENU_LAYOUT); }
        break;
    case UI_KEY_OK:
        app_send_message(APP_MSG_MUSIC_PP, 0);    /* 业务交给 app 层 */
        break;
    case UI_KEY_MODE:
        ui_hide_main(ID_WINDOW_BT);
        ui_show_main(ID_WINDOW_SYS);
        break;
    default:
        return false;      /* 不认的键往下传 */
    }
    return true;           /* 认了就吃掉 */
}
```

### 触摸

```c
struct touch_event { int event; int x; int y; int has_energy; };
int ui_touch_msg_post(struct touch_event *event);
```

控件侧挂 `.ontouch`，事件类型见工程 json `action` 属性里的枚举
（`TOUCH_DOWN` 129 / `TOUCH_UP` 130 / `TOUCH_MOVE` 131 / `TOUCH_HOLD` 132 /
`TOUCH_CLICK` 133 / `TOUCH_DOUBLE_CLICK` 134）。
滑条的拖动可以直接转给 `slider_touch_slider_move(slider, e)`。

---

## 5. 各控件的 API 一览

所有 `*_by_id()` 都用 ID 头里的宏当 `id`，不需要先拿控件指针 ——
**页面代码优先用 `_by_id` 版本**；带结构体指针的版本用在回调里（`ctrl` 就是那个指针）。

```c
/* 文字 ui/ui_text.h */
int ui_text_show_index_by_id(int id, int index);
int ui_text_set_text_by_id (int id, const char *str, int len, u32 flags);
int ui_text_set_textu_by_id(int id, const char *str, int len, u32 flags);          /* UTF-8 */
int ui_text_set_textw_by_id(int id, const char *str, int len, int endian, u32 flags);
int ui_text_set_str_by_id  (int id, const char *format, const char *str);

/* 图片 ui/ui_pic.h */
int ui_pic_show_image_by_id(int id, int index);
int ui_pic_set_image_index(struct ui_pic *pic, int index);      /* 不触发重绘，可在 INIT 用 */
int ui_pic_set_hide_by_id(int id, int hide);
int ui_pic_get_normal_image_number_by_id(int id);

/* 数字 ui/ui_number.h */
int ui_number_update_by_id(int id, struct unumber *n);

/* 时间 ui/ui_time.h */
int ui_time_update_by_id(int id, struct utime *time);

/* 电池 ui/ui_battery.h */
int  ui_battery_set_level_by_id(int id, int persent, int incharge);
void ui_battery_level_change(int persent, int incharge);

/* 滑条 ui/ui_slider.h、ui/ui_slider_vert.h */
int ui_slider_set_persent_by_id(int id, int persent);   /* 0..100 */
int slider_get_percent(struct ui_slider *slider);

/* 圆环进度 ui/ui_progress.h */
int ui_progress_set_persent_by_id(int id, int persent);

/* 列表 ui/ui_grid.h */
int  ui_grid_highlight_item_by_id(int id, int item, bool yes);
int  ui_grid_set_item_num(struct ui_grid *grid, int item_num);
int  ui_grid_slide(struct ui_grid *grid, int direction, int steps);
void ui_grid_on_focus(struct ui_grid *grid);
void ui_grid_lose_focus(struct ui_grid *grid);

/* 高亮（通用） ui/ui.h */
int ui_highlight_element_by_id(int id);
int ui_no_highlight_element_by_id(int id);
int ui_invert_element_by_id(int id);
```

### 彩屏专有

```c
/* 页面滑动切换 ui/ui_page_switch.h */
int ui_page_switch(int curr_win, int next_win, int xoffset, int mode);
int ui_page_move(int curr_win, int xoffset, int yoffset, int mode);
int ui_page_scale(int curr_win, int next_win, int dir);

/* 转场特效 ui/ui_effect.h */
int ui_window_effect(int id, u16 effect_mode, void *user_effect, void *effect_priv);
int ui_page_auto_sw_effect(int curr_win, int next_win, u16 mode, void *cb, void *priv);
void ui_window_stop_redraw(int stop_redraw);

/* 背光 ui/ui_api.h */
void ui_backlight_open(u8 recover_cur_page);
void ui_backlight_close(void);

/* 歌词 ui/lyrics.h、文件浏览 ui/ui_browser.h */
```

⚠ 特效和页面滑动会**整帧重新合成**，在没有 PSRAM 的板子上很贵。
`imb_task_head` 里那一组 `copy_to_psram` / `effect_mode` 字段就是为它准备的，
详见 `platform.md`。
