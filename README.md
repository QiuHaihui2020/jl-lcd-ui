# jl-lcd-ui

杰理（JL）**彩屏** UI 开发的 Claude Code Skill。

适用于 JL SDK 里走 `ui_framework` + UITools 的彩屏界面：图层 `color_format = OSD16`，
设备端由 **IMB 硬件图层合成**出帧再推屏（SPI / MCU / RGB 屏，如 st7789）。

单色点阵屏（`OSD1`，软件 framebuffer）是**另一条完全不同的路径**，看
[jl-dot-ui](https://github.com/QiuHaihui2020/jl-dot-ui) —— 两套有好几条结论是相反的。

---

## 这个 skill 解决什么

UITools 是纯 GUI，没有可脚本化的命令行；工程文件是几 MB 的 JSON，直接 grep 看不懂结构；
控件 ID 是位域、要人工点「生成」才会吐 `ename.h`。于是 AI 改界面时最容易出的问题是：
**改完了不知道对不对，要等人工导出 + 烧录才发现。**

这个 skill 做三件事：

1. **把设备端的实际行为写清楚**，而且标明来源 —— 每条结论都注明是怎么得到的，
   哪些是确定的、哪些是特定版本上实测的、哪些还没查清楚。
2. **补上工具链缺的那几环**：算控件 ID、语义体检、从 json 渲染整页做排版自检。
3. **把踩过的坑固化下来**，尤其是那些「代码看着对、就是没反应」且不报任何错的。

---

## 安装

作为**项目级** skill（只对某个工程生效）：

```bash
cd <你的 SDK 工程>
mkdir -p .claude/skills
git clone https://github.com/QiuHaihui2020/jl-lcd-ui.git .claude/skills/jl-lcd-ui
```

作为**个人级** skill（对所有工程生效）：

```bash
git clone https://github.com/QiuHaihui2020/jl-lcd-ui.git ~/.claude/skills/jl-lcd-ui
```

装好后 Claude Code 会在做彩屏 UI 相关的活时自动加载，也可以直接 `/jl-lcd-ui` 调用。

---

## 目录

```
SKILL.md              主文档：工作循环、八条铁律、控件表
reference/
  widgets.md          选控件：每个控件什么时候用、限制、代码怎么调
  authoring.md        建工程 / 搭结构：目录、从控件库造节点、弹层怎么做
  project.md          改 .json：树结构、类型码、ID 规则、坐标、各类属性
  app.md              写代码：事件注册、生命周期、控件 API、窗口/弹层/消息/按键
  assets.md           素材：字号反推、复用既有图标、透明区检查、排版自检
  platform.md         查现象：IMB 合成、图层 buffer、图片格式、屏驱动、分辨率
  export.md           导出 / 烧录：GUI 两步、copy_file.bat、res 分区打包
tools/
  jlui.py             公共解析层（类型码表、遍历、ID 计算）
  dump_tree.py        把几 MB 的工程 json 打成可读的树（带算出来的 ID）
  check_project.py    语义体检，有错误返回 1
  gen_ename.py        从 json 算 ename.h；--check 和现有头文件比对
  render_page.py      从 json 渲染整页做排版自检（需要 pillow）
```

排一个新界面的顺序：`widgets.md` 选控件 → `authoring.md` 搭结构 →
`project.md` 落成 json → `app.md` 写回调 → `export.md` 导出。

---

## 脚本用法

```bash
# 看结构（不要 grep 工程文件）
python tools/dump_tree.py <工程.json>              # 所有页概览
python tools/dump_tree.py <工程.json> -p 4         # 只看第 4 页
python tools/dump_tree.py <工程.json> -p 4 --props # 再加上专有属性

# 语义体检：有错误退出码 1
python tools/check_project.py <工程.json>

# 算控件 ID，和应用侧头文件比对（不用等人工导出就能接着写代码）
python tools/gen_ename.py <工程.json> --check apps/soundbox/include/ui/style_JL_new.h

# 排版自检：直接渲染出图，别手敲坐标画效果图
python tools/render_page.py <工程.json> 3 -o out.png --sample CLOCK_TIME_HMS=15
```

`jlui.py` / `dump_tree.py` / `check_project.py` / `gen_ename.py` **零依赖**；
只有 `render_page.py` 需要 `pip install pillow`。

`check_project.py` 和 `gen_ename.py` 都拿两个真实工程标定过
（0 错误 / 572 个 ID 全中），**它们一旦报错就是真错**，不要当噪音跳过。

---

## 几条最值钱的结论

摘自 `SKILL.md`，完整版连同依据看文档本身。

- **控件 ID 是纯算出来的**：`(工程号<<26) | (页下标<<17) | (类型码<<10) | 同页同类型序号`。
  推论是**往一页中间插控件会把后面同类型控件的 ID 全推后一位** ——
  插完必须跑 `gen_ename.py --check`；加在页末尾则不影响已有 ID。

- **`caption` 决定控件类型，不是 `-type`**。slider / progressbar 这些组合控件的零件
  `-type` 全是 `ImageList`，靠 `caption` 才被认成零件。**顺手"整理" caption
  会让它静默退化成普通图片，而且整页同类型控件的 ID 跟着错位。**

- **绘制期回调里不能调 `*_by_id()` 去刷别的控件**，包括 `ON_CHANGE_INIT`。
  会重入绘制递归、冲掉资源管理器里唯一那份 `static union ui_control_info`，
  症状是**整棵子树画不出来**。反过来，在消息回调 / 定时器 / 按键处理里
  **必须直接调**，那里 `ui_set_call()` 的上下文句柄是空的，调用会被静默丢弃。
  两个方向都不报错。

- **`element is null` 警告不是噪声**，是"这次调用被吞了"的回执 ——
  同一段代码在不同页上表现完全不同，取决于目标控件在遍历顺序里排在前还是后。

- **`slider` / `vslider` / `grid` 会消费方向键**并返回 1 中止分发，
  症状是"确认键正常、只有方向键失灵"，看着像按键驱动坏了。

- **要透明就写空串**，别照抄现有工程的 `#ffffffff`（编辑器预览和实机对不上，
  而且在某些版本上它根本不是"不填充"，见 `platform.md` §5 的实测记录）。

---

## 关于文档里的「依据」

这个 skill 刻意区分三种可信度，读的时候注意措辞：

| 说法 | 含义 |
|---|---|
| 「从框架实现读到的」 | 确定的行为，文档里给了怎么自己再查一遍 |
| 「在板子上量到的」 | 具体硬件 + 具体 SDK 版本上的实测，换版本要自己复验 |
| 「根因没定位到」 | 就是没查清楚，连同已排除的可能一起记着，免得下次重查 |

没有第四种「应该是这样」。

---

## 作者

本 skill 的文档和脚本由 **Claude Opus 5**（Anthropic）编写，
在真实的杰理彩屏工程上边做界面边整理、逐条验证而成。

