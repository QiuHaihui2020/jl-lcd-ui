# 做完界面怎么导出、怎么进固件

⚠ **这套工具链没有可脚本化的导出命令行**，`ui-tools.exe` 和 `QtToolBin.exe`
都是 Qt GUI。AI 不要去调这两个 exe，也不要试图用命令行参数驱动它们
（strings 里没有任何可用选项）。导出是**人工两步**。

---

## 1. 整条链

```
<工程>.json
   │  ① ui-tools.exe（step1）保存工程
   ├─► ename.h               控件 ID 头
   └─► ResBuilder.xml        打包配置（图片清单、颜色表、excel 路径）
                             ⚠ 里面的 <Fonts> 不是 strpic 的字号，见 §6
   │
   │  ② QtToolBin.exe（step2）生成资源
   ├─► project.bin           布局（二进制）
   ├─► result.bin            图片资源
   ├─► result.str            字符串图片
   └─► result_pic_index.h / result_str_index.h / result.h / res_ver.h / result.csv
   │
   │  ③ copy_file.bat（工程目录下，step2 里点"生成"通常会自动调）
   │     先 style_table.exe -stylefile project.bin -prj 0x0   ← 打上工程号
   ├─► <tools>/JL_LCD/JL.sty                     ← 布局
   ├─► <tools>/JL_LCD/JL.res                     ← 图片
   ├─► <tools>/JL_LCD/JL.str                     ← 字符串
   └─► apps/soundbox/include/ui/style_JL_new.h   ← ID 头（由 ename.h 拷过来）
   │
   │  ④ download.bat（烧录时）
   └─► res 分区 / 外挂 flash 镜像
```

`copy_file.bat` 是**每个工程自己的**，就在 `project/` 下，可以改。
典型内容：

```bat
..\..\..\UITools\style_table -stylefile project.bin -prj 0x0
copy .\project.bin ..\..\..\..\JL_LCD\JL.sty
copy .\result.bin  ..\..\..\..\JL_LCD\JL.res
copy .\result.str  ..\..\..\..\JL_LCD\JL.str
if exist "..\..\..\..\..\..\..\apps\soundbox\include\ui\" (
    copy .\ename.h ..\..\..\..\..\..\..\apps\soundbox\include\ui\style_JL_new.h
)
```

有的工程还会拷 `result_pic_index.h` / `result_str_index.h`，
并且用 `FileCompare.exe` 判断内容有没有变（没变就不拷，避免无谓的全量重编译）。

## 2. ⚠ ID 头和资源必须是同一次导出的

`JL.sty` 里存的是那一次生成出来的 ID。**只换资源不换头（或反过来），
控件全找不到** —— 界面一片空白或只剩背景，而且不报错。

推论：

- `style_JL_new.h` 是**生成物**，不要手改，改了下次导出就没了。
- 业务别名写 `ui_style.h`（手写、进版本库）。
- 版本库里 `style_JL_new.h` 和 `JL_LCD/*` 要一起提交。

## 3. ⚠ 同一套工具下的多个工程会互相覆盖

`<tools>/JL_LCD/` 和 `style_JL_new.h` 这两个目标路径，
**同一套 UITools 下的几个工程往往写的是同一个地方**。
在 B 工程里点一次「生成」，固件用的就变成 B 的界面了。

排查"谁改了 `style_JL_new.h`"时先想到这个。动手前确认：

1. 自己在哪个工程目录里（`project/` 的上两级）
2. `Application Data/ui-config` 的 `LastOpen` 是不是这个工程的 json
3. `copy_file.bat` 里的目标路径是不是你要的

## 4. 不打开 GUI 能做什么

| 想确认的事 | 能不能不开 GUI | 怎么做 |
|---|---|---|
| json 结构/属性写对了没 | **能** | `tools/check_project.py` |
| 控件 ID 是多少、有没有变 | **能** | `tools/gen_ename.py [--check <ID头>]` |
| 树长什么样、坐标对不对 | **能** | `tools/dump_tree.py -p <页>` |
| 排版好不好看 | 不能 | 只能开 `ui-tools.exe` 看，或上板 |
| 生成 `.sty`/`.res` | 不能 | 必须 `QtToolBin.exe` |

所以正确的分工是：**能静态查的全部查干净，再交给人点那两下。**
交接时把「改了哪几页、新增/改名了哪些 ename、ID 有没有位移」一起说清楚。

## 4.5 编辑器预览里这几样是正常的，不是控件坏了

`ui-tools.exe` 的画布是**静态预览**，不跑设备端逻辑。下面几条是既定行为，
第一次看到容易误判成"控件做坏了"：

| 现象 | 真相 |
|---|---|
| Time / Number 一律显示**单个 `0`** | 不按 `format` 展开。满屏 `0` 是正常的 |
| ImageList 只显示**列表第 0 张** | 切 index 是运行时的事 |
| slider 显示 **100%** | 填充长度是运行时按百分比算的 |
| 控件背景是一块不透明白 | 多半是 `background_color` 写了 `#ffffffff`（见 SKILL.md 铁律 4） |

反过来，**编辑器对 PNG 的 alpha 处理是正确的** —— 透明区会透出底下控件的颜色，
不是白/黑方块。所以看到"图标周围一圈色块"时，
**先查 `background_color`，不要先怀疑 PNG 格式**。

## 5. 资源怎么进固件：两条路

由 `app_config.h` 的 `TCFG_UI_RES_MEDIUM` 决定，`download.c` 生成的
`download.bat` 里按它分流：

### 路 A：内置 flash 资源区（`UI_RESOURCE_EN=1`）

```bat
copy ..\..\JL_LCD ..\..\JL
set UI_RESOURCE_FILE=..\..\JL ..\..\font
...
isd_download.exe ... -res %UI_RESOURCE_FILE% ...
```

资源目录直接打进内置 flash 的资源区，运行时路径 `flash/res/`。
简单，但占内置 flash。

`UI_RESOURCE_EN=2` 是 OLED（点阵）那套，拷的是 `JL_OLED/`。

### 路 B：外挂 flash 虚拟 FAT 镜像（`UI_EXFLASH_EN=1`）

```bat
packres.exe -keep-suffix-case JL.sty JL.res JL.str -n res -o JL
packres.exe -keep-suffix-case F_ASCII.PIX F_UNIC.PIX ascii.res -n res -o font
fat_comm.exe -pad-backup2 -force-align-fat -out new_res.bin ^
             -image-size %EX_FLASH_IMAGE_SIZE% -filelist JL font -remove-empty -remove-bpb
packres.exe -n res -o res.bin new_res.bin 0 -normal
isd_download.exe ... -ex_flash res.bin ...
```

资源打成 FAT 镜像烧到外挂 flash。彩屏资源动辄几百 KB，一般走这条。

⚠ **外挂 flash 容量只在 `user_config.h` 的 `CONFIG_EXTERN_FLASH_SIZE` 配一次**，
经 `EX_FLASH_IMAGE_SIZE` 传给 `fat_comm -image-size`。
两处改不一致会导致镜像大小和实际容量对不上。

## 6. 多国语言表 —— 加新文案是人工活

文字内容不在工程 json 里，在 `UITools/多国语言_*.xls`（路径由工程根的
`lang_excel` 和 `ResBuilder.xml` 的 `<excel_path>` 指定）。

- Text 控件的 `str.list` 里放的是表里的**条目 id**（`m1` `m30` …）。
- 表里一行一个 id，一列一种语言。
- 改了表要重跑 step2 才会进 `JL.str`。
- 生成出来的 `result_str_index.h` 里是 `#define M1 1` 这样的索引，
  应用代码一般用不到（走 `ui_text_show_index_by_id` 的 index 而不是这个宏）。

⚠ `str.list` 里写了表里没有的 id：**不报错**，运行时那条就是空白。

### ⚠ AI 加不了新文案，两条出路

`.xls` 是二进制文件，**只能人工开表格改**。所以"给界面加一句新文案"
这件事，AI 做不完整。两个办法：

| 办法 | 怎么做 | 代价 |
|---|---|---|
| 人工加 | 开 `多国语言_*.xls` 加一行，记下新 id，填进 `str.list`，重跑 step2 | 要人；但跟随语言切换 |
| **预渲染成图片** | 自己把文案渲染成 PNG，用 `ImageList` 摆上去 | **不跟随语言切换** |

第二条是完全正当的做法，不是将就 —— 因为固定文案本来走的就是
"资源生成时离线渲染成位图"这条路（见 `platform.md` 第 6 节），
自己渲染只是换了个渲染的人。对"最高温度""周六""℃"这类固定标签尤其合适，
还顺带绕开了字库不一定有那个字形的问题。

**多语言产品就老老实实改 xls。**

### ⚠⚠ 字号也在 xls 里 —— 是**单元格自己的字号**，不是 `<Fonts>`

`ResBuilder.xml` 里那 22 个 `<fontNN lfHeight="-16"/>` 看着像字号配置，
**改它对 strpic 完全没用**。要改固定文案字号只有一条路：开 Excel 全选改字号，
存成 `.xls`(BIFF8，别存成 xlsx)，重跑 step2 + `copy_file.bat`。
完整实测证据见 `platform.md` §6。

⚠ 同一行不同语言列可以是不同字体，**行高要按最高的那个留**。
实测样例工程里少数条目用的是 Times New Roman，同样 24 号下位图高 27 而不是 24。

## 6.5 烧录前验字号：直接解析 `JL.str`

改完字号**不要靠上板看**。`JL.str` 的格式很简单，解析出来就知道每条文案的位图多大：

```
0x00  "RU40" 魔数 + 头部
0x20  起，每条 20 字节：
      u16 lang   语言编号（见 font/language_list.h，1=简体中文）
      u16 id     字符串编号，对应 project/result_str_index.h 的 #define M42 <id>
      u16 width  位图宽
      u16 height 位图高
      u32 len    数据长度，等于 width*height/8（1bpp，可用来自检解析对不对）
      u32 offset 数据偏移
      u32 crc
```

```python
import struct
d = open('JL.str','rb').read()
off = 0x20
while off + 20 <= len(d):
    lang, sid, w, h, ln, o, crc = struct.unpack_from('<HHHHIII', d, off)
    if o == 0 or o > len(d) or not (0 < w < 1000) or not (0 < h < 200):
        break
    ...
    off += 20
```

配合 `result_str_index.h`（`#define M31 9` 这样的 m 号→id 映射）就能精确对到
每个 Text 控件，算出**哪些文案会超出 rect** —— 比上板一页页看快得多。

两个实测出来的判据：

- **`git diff` 是空的就是没生效。** `JL.str` 在版本库里，改完字号重新生成后
  如果 `git diff` 没有变化，说明这次生成完全没受影响（mtime 变了不算数）。
- **`m*.png` 不能当依据。** `config/` 下那批中间产物**不一定跟着 step2 更新**，
  实测跑完 step2 之后它们还是一个月前的时间戳。

## 7. 字库是另一份资源，和 xls 那条路也无关

运行时字符串（`ui_text_set_text_by_id()` 放歌名这类）走的是设备端点阵字库，
**不是** `ResBuilder.xml` 里配的那个字体：

```
LCD_UI工程/字库工具/FontTool.exe + font.xml
        ↓
   F_ASCII.PIX / F_UNIC.PIX / ascii.res
        ↓  烧录脚本单独打包
   packres.exe -keep-suffix-case F_ASCII.PIX F_UNIC.PIX ascii.res -n res -o font
```

所以两条路的字号是**分别配、分别改**的：

| | 固定文案（strpic） | 运行时字符串（text/ascii） |
|---|---|---|
| 字号配在哪 | xls 单元格的字号 | `字库工具/font.xml` 的 `<FontSize Value="24"/>` |
| 改完要跑什么 | step2 + `copy_file.bat` | `FontTool.exe` 重出 `.PIX` |

⚠ 这两处**不会自动对齐**，实测踩过：字库已经是 24 号（歌名显示正常），
xls 还是 12 号，于是同一个界面上歌名 24 号、列表文字 12 号。
「只有一部分文字变大了」就是这个症状。

## 7.5 导出后的自检：`result.xml` + `JL.res` 增量

这两样**不用跑任何 exe** 就能确认导出结果，是 AI 能做的最后一道关。

### `result.xml`：每张图被打成什么格式，一目了然

导出后 `project/result.xml` 里每张图一行明文：

```xml
<Picture format="ARGB8565" id="30">…\config\pic_clock\AQI_0.png</Picture>
<Picture format="RGB565"   id="33">…\config\pic_lcd\RTC_NUM_0.bmp</Picture>
```

```sh
# 确认格式分布和预期一致（比如新加的 77 张透明图是不是都按 ARGB8565 打包）
grep -oE '<Picture format="[A-Za-z0-9]+"' result.xml | sort | uniq -c
```

透明图被打成 `RGB565` 就是 alpha 丢了 —— 在这一步能抓住，不用等上板。

### `JL.res` 的增量：真实 flash 占用

资源包是压缩的，`platform.md` 里那个"像素数 × 3 B"只是**上界**。
真实占用就量文件大小差：

```sh
# 导出前后各记一次
ls -l cpu/<芯片>/tools/JL_LCD/JL.res
```

实测过一次：裸算 322 KB 的一批图，`JL.res` 实际只涨了约 92 KB（压缩比 ~3.5×）。
**所以"放不下"这个判断要以这个增量为准，不要用裸算吓自己。**

## 8. 验收清单

导出并烧录后，按这个顺序确认：

1. `git diff` 看 `JL_LCD/*` 和 `style_JL_new.h` **是不是一起变的** ——
   只变一个就是上面第 2 条的问题
2. `python tools/gen_ename.py <工程.json> --check apps/.../style_JL_new.h`
   应当 0 差异（证明拷过去的头就是这个工程的）
3. 编译，确认应用代码里用到的 ename 都还在（改名/删控件会是编译错误，这是好事）
4. 上板：先看页面能不能画全，再逐个弹层试按键

`res_ver.h` / `result_*_index.h` 头部有 `Generated By ... <时间>` 行，
`.sty` 头部也有时间戳 —— **比对产物时这几处必然不同，其余应当一致**，
别把时间戳差异当成"资源变了"。

## 9. 提交前三查：别提交出"工程新、资源旧"

改了界面又改了素材时，很容易只提交其中一半。三条各自独立，都要过：

| 查什么 | 怎么查 | 不过说明 |
|---|---|---|
| 工程 ↔ ID 头 | `gen_ename.py <工程> --check <ID头>` 零差异 | 头文件不是这个工程导出的 |
| `result.xml` 条目数 ↔ 素材目录文件数 | 两边数一遍（实战：97 ↔ 97） | 有图没进打包，或有图没删干净 |
| `JL.res`/`res.bin` 时间戳 ↔ 工程 json 时间戳 | 资源应当**不早于**工程 | 改完工程忘了重新导出 |

### ⚠ 还要查素材有没有被 .gitignore 挡掉

工程的 `config/.gitignore` 里通常有 `*.png`，靠白名单逐个放行子目录：

```gitignore
*.png
!ctrl/*
!ini/*
!pic_clock/*        ← 新建的素材目录必须自己加一行
```

**忘了加白名单，那批图一张都进不了版本库**。后果很隐蔽：
仓库里只剩编译好的 `JL.res` 二进制，别人 checkout 下来**能烧录、但改不了界面**，
而且可能隔好几个提交才被发现。

```sh
git check-ignore -v <素材目录>/xxx.png     # 应该没有输出
git ls-files <素材目录> | wc -l            # 应该等于目录里的文件数
```

详见 `assets.md` 第 6 节。
