# Daily Stoic → 80mm 热敏打印机

每天早上 9 点，自动抓取当日最新一篇 **Daily Stoic** 邮件冥想，排版成 80mm 热敏小票打印出来，
正文之后附**当日生词/短语表（含中文释义）**，用于英语学习和雅思备考。

```
================================================
                  DAILY STOIC
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
   n. 差事；跑腿
   Working, some part of us is thinking about
   the errands we need to run later or the
   conversation we had the other day.
...
================================================
```

## 结构

| 文件 | 作用 |
|---|---|
| `fetch_latest.py` | 抓最新邮件文章 → Markdown（含图片下载） |
| `receipt.py` | 80mm 排版 + ESC/POS 编码（中英混排，按显示宽度换行） |
| `daily_print.py` | 主程序：抓取 → 挑生词 → 排版 → 发送打印机 |
| `build_data.py` | 下载并构建本地词频表 + 英汉词典 |
| `com.dnevend.dailystoic.print.plist` | macOS 定时任务（每天 9:00） |

## 依赖

- Python 3.9+（无第三方库）
- macOS 自带 `lp`（USB 打印机队列方式使用）

## 首次准备

```bash
python3 build_data.py          # 下载高频词表 + ECDICT 英汉词典，生成 data/
```

## 用起来

```bash
# 抓文章存成 Markdown（可选，用于自己看）
python3 fetch_latest.py 3

# 排版预览（不打印）
python3 daily_print.py --preview preview.txt --no-print

# 打印到网络打印机（推荐：免驱动，直接发 ESC/POS 到 9100）
python3 daily_print.py --ip 192.168.1.50

# 打印测试页（检查宽度、对齐、切纸）
python3 daily_print.py --ip 192.168.1.50 --test

# USB（先建好 CUPS 队列）
python3 daily_print.py --queue XP-80T
```

## 每天 9:00 自动打印

```bash
cp com.dnevend.dailystoic.print.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.dnevend.dailystoic.print.plist
launchctl start com.dnevend.dailystoic.print     # 立即跑一次验证
```

日志在 `logs/`，每次打印的文本留档在 `prints/`。

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--width` | 48 | 每行字符数（80mm Font A ≈ 48） |
| `--words` | 8 | 生词表条数 |
| `--common` | 6000 | 前 N 个高频词视为"已认识"；调低＝生词更多更简单 |
| `--no-vocab` | — | 不印生词表 |
| `--no-zh` | — | 不印中文释义（打印机不支持中文时用） |
| `--ip` / `--queue` | — | 网络打印机 IP / CUPS 队列名 |

也可以写 `config.json`（见 `config.example.json`），命令行参数优先级更高。

## 打印机连接

**网络（推荐）**：打印机插网线，按住 `FEED` 开机打自检页拿到 IP；
建议在路由器上给打印机绑定静态 IP，避免 IP 变化导致定时任务失败。

**USB**：`lpinfo -v | grep -i usb` 看设备 URI，再建一个 raw 队列：

```bash
lpadmin -p XP-80T -E -v "<usb://...>" -m raw
```

## 数据来源

- 文章：<https://dailystoic.com>（标题含 `Daily Stoic Emails` 分类），仅供个人学习，请勿再分发
- 词频：Google 10k（[first20hours/google-10000-english](https://github.com/first20hours/google-10000-english)）
- 词典：[ECDICT](https://github.com/skywind3000/ECDICT)

词汇表基于词频与词形还原自动挑选，仅作学习参考。

## License

代码采用 [MIT License](LICENSE)。

本仓库**不包含**抓取的 Daily Stoic 文章、词频表与 ECDICT 词典数据（均已被 `.gitignore` 忽略），
请自行运行 `build_data.py` / `fetch_latest.py` 获取，并遵守各自来源的使用条款。
