# Daily Stoic → 80mm 热敏打印机

每天早上 9 点，自动抓取当日最新一篇英文文章（默认 **Daily Stoic** 的每日冥想），
排版成 80mm 热敏小票打印出来，正文之后附**当日生词表（含中文释义）**，用于英语学习和雅思备考。

```
================================================
                  DAILY PRINT
                    2026-10-17
================================================

            Let Each Sphere Come First

------------------------------------------------

Think about how rarely we give ourselves fully
to whatever we're doing. ...

------------------------------------------------
TODAY'S WORDS
------------------------------------------------
1. errands
   n. 任务, 差使, 使命
   Working, some part of us is thinking about
   the errands we need to run later or the
   conversation we had the other day.
...
================================================
source: https://dailystoic.com/let-each-sphere-come-first/
printed: 2026-10-18 09:00
================================================
```

## 特性

- **多来源**：内置 Daily Stoic 抓取器 + 通用 RSS/Atom 来源，加新来源只需写一个类或一段配置
- **生词表**：按词频挑出「超出你词汇量」的词（含词形还原），配原文例句
- **中文释义**：本地英汉词典（ECDICT，40 万词条），离线可用，屈折词自动回退原形
- **中英混排排版**：按**显示宽度**换行（中文算 2 列），中文走 GB18030 中文模式
- **两种打印机接入**：网络 9100 端口直发（免驱动）/ CUPS 队列（USB）
- **可测试**：纯函数排版 + pytest 测试，无需打印机即可验证
- **长文保护**：正文超过 `max_words`（默认 900 词）时打印截断，存档仍保留全文

## 安装

```bash
git clone git@github.com:Dnevend/daily-stoic-printer.git
cd daily-stoic-printer

uv venv
uv pip install -e ".[dev]"        # 或 make install

# 首次准备：下载高频词表和英汉词典到 data/
.venv/bin/dailyprint build-data
```

无第三方运行时依赖，只用标准库。

## 快速开始

```bash
# 看看有哪些来源
.venv/bin/dailyprint sources

# 排版预览（不打印）
.venv/bin/dailyprint preview -o preview.txt

# 直接打印（网络打印机）
.venv/bin/dailyprint --config config.toml print --ip 192.168.1.50

# 打测试页（校准宽度/对齐/切纸，含中文测试行）
.venv/bin/dailyprint test-print --ip 192.168.1.50

# 抓文章存成 Markdown（可选，--images 会把图片下到本地）
.venv/bin/dailyprint fetch --count 3 --images
```

## 命令一览

| 命令 | 作用 |
|---|---|
| `sources` | 列出已配置的来源与可用类型 |
| `build-data [--force]` | 下载并构建词频表 / 词典 |
| `fetch [--count N] [--images]` | 抓文章存 Markdown |
| `preview [-o FILE]` | 排版预览 |
| `print [--ip IP \| --queue NAME] [--dry-run]` | 抓取 + 排版 + 发送 |
| `test-print` | 发送测试页 |

通用参数：`--source`、`--width`、`--words`、`--common`、`--max-words`、`--no-vocab`、`--no-zh`、`--config`、`-v`。

## 配置

复制 `config.example.toml` 为 `config.toml`：

```toml
[defaults]
source = "daily-stoic"

[render]
width = 48
words = 8
common = 6000
chinese = true

[printer]
kind = "network"
ip = "192.168.1.50"
port = 9100

[sources.daily-stoic]
type = "daily_stoic"
base_url = "https://dailystoic.com"
```

也可用环境变量：`DAILYPRINT_HOME`、`DAILYPRINT_SOURCE`、`DAILYPRINT_PRINTER_IP`。

## 加一个来源

**方式一：RSS（零代码）** —— 大多数字体/博客都有 feed：

```toml
[sources.marginalian]
type = "rss"
url = "https://www.themarginalian.org/feed/"
```

```bash
.venv/bin/dailyprint preview --source marginalian
```

**方式二：写一个类**（源站没有 feed，或需要抓取/解析特殊结构）：

```python
# src/dailyprint/sources/myblog.py
from ..models import Article
from .base import Source
from .http import get_text

class MyBlogSource(Source):
    def __init__(self, name="myblog", base_url="", **_):
        super().__init__(name)
        self.base_url = base_url

    def latest(self, count=1):
        html = get_text(self.base_url)
        ...  # 解析出 title / date / 正文
        return [Article(source=self.name, title=..., url=..., date=..., text=..., raw=...)]
```

然后在 `src/dailyprint/sources/__init__.py` 的 `TYPES` 里注册，并在 `config.toml` 写：

```toml
[sources.myblog]
type = "myblog"
base_url = "https://example.com/"
```

新增来源建议顺手在 `tests/` 里加一个用 fixture HTML 的解析测试（不联网）。

## 打印机连接

**网络（推荐）**：打印机插网线 → 按住 `FEED` 开机打自检页拿到 IP →
建议在路由器给它绑定静态 IP，避免 IP 变化导致定时任务失败。

```bash
.venv/bin/dailyprint test-print --ip 192.168.1.50
```

**USB**：建一个 raw 队列，然后用 `--queue`：

```bash
lpinfo -v | grep -i usb        # 找到设备 URI
lpadmin -p XP-80T -E -v "<usb://...>" -m raw
.venv/bin/dailyprint test-print --queue XP-80T
```

## 每天早上 9:00 自动打印

```bash
cp com.dnevend.dailystoic.print.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.dnevend.dailystoic.print.plist
launchctl start com.dnevend.dailystoic.print     # 立即跑一次验证
```

日志在 `logs/`，每次打印的文本留档在 `prints/`（即使打印失败也不丢内容）。
Mac 睡眠时错过的任务会在唤醒后补跑。

## 项目结构

```
src/dailyprint/
├── cli.py            命令行入口（sources / build-data / fetch / preview / print / test-print）
├── config.py         配置（TOML + 环境变量）
├── models.py         Article / VocabItem / Issue
├── pipeline.py       来源 -> 文章 -> 生词 -> 一期内容
├── storage.py        存档（文章 Markdown、打印副本）
├── textutil.py       显示宽度、混排换行、HTML/Markdown 清理、词形还原
├── sources/          内容来源：base（基类）、daily_stoic、rss、http
├── enrich/           生词挑选（vocab）、词典查询（dictionary）
├── render/           80mm 排版（receipt）、ESC/POS 编码（escpos）
└── printers/         打印机：network（9100）、cups（lp -o raw）
tests/                pytest 测试（含 HTML/feed fixture，不联网）
```

想扩展的地方基本都是「加一个文件 + 注册一行」：来源在 `sources/`，打印机在 `printers/`，
排版规则在 `render/receipt.py`，生词策略在 `enrich/vocab.py`。

## 开发

```bash
make test        # pytest
make lint        # ruff
```

## 数据来源

- 文章：<https://dailystoic.com>（`Daily Stoic Emails` 分类），仅供个人学习，请勿再分发
- 词频：Google 10k（[first20hours/google-10000-english](https://github.com/first20hours/google-10000-english)）
- 词典：[ECDICT](https://github.com/skywind3000/ECDICT)

词汇表基于词频与词形还原自动挑选，仅作学习参考。

## License

代码采用 [MIT License](LICENSE)。

本仓库**不包含**抓取的文章、词频表与词典数据（均被 `.gitignore` 忽略），
请自行运行 `build-data` / `fetch` 获取，并遵守各自来源的使用条款。
