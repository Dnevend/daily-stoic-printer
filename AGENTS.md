# daily-stoic — Agent 指南

每天早上 9 点抓取当天一篇英文文章（默认 Daily Stoic 的每日冥想），排版成 80mm 热敏小票打印：
封面 → 正文 → 中文译文 → 生词表（含中文释义）。用于英语学习与雅思备考。

远程：`git@github.com:Dnevend/daily-stoic-printer.git`。包名 `dailyprint`，要求 Python 3.11+。

## 常用命令

```bash
make install        # 建 venv 并安装依赖
make test           # .venv/bin/pytest
make lint           # .venv/bin/ruff check .
make fmt            # .venv/bin/ruff format .
make preview        # 生成 preview.txt，不打印
make fetch          # 抓取文章
make build-data     # 构建词典 / 词频数据
```

## 结构

- `src/dailyprint/` — 主包；CLI 入口 `dailyprint.cli:main`
- `tests/` — pytest 用例，`tests/fixtures/` 放样例数据
- `articles/` `prints/` `logs/` `data/cache/` — 生成物，均不入库
- `config.toml` — 本机配置，样例见 `config.example.toml`
- `com.dnevend.dailystoic.print.plist` — LaunchAgent，每天 9:00 触发

## 硬约束

- 绝不提交：`articles/`、`prints/`、`logs/`、`data/*.csv`、`data/*.tsv`、`data/state.json`、`config.toml`、`.venv/`
- 抓取的正文是第三方内容，个人学习用途，不入库
- 提交前跑 `make test` 和 `make lint`

## 已知限制（真机联调得出，改代码前先看）

目标机型是 **XPrinter XP-80T**（80mm、ESC/POS、网口 9100）。实测问题：

1. **位图命令头必须是小写 `v`**：`GS v 0 m` = `1D 76 30 00`。原实现写成大写
   `1D 56 30 00`（`GS V 48`＝切纸），真机表现为「先切一刀，随后整段位图被当文本
   打成乱码」。已修正。历史记录的「单独发正常、夹在文章里成噪点」很可能是同一
   bug 的变体，未复测；**改图片相关代码后要在真机上验证再默认打开**。
2. **位图建议单条命令**：`image_to_raster()` 一次发完整张图。多条 `GS v 0` 的
   乱码结论是在命令头写错的前提下得出的，未复测，保守保持单条。
3. 中文模式用 `FS &`（`1C 26`）+ GB18030；位图前不要额外插入切纸/复位命令。
4. **launchd 里不能用 Python 直连局域网**：macOS「本地网络」隐私会静默拒绝未
   系统签名的进程（`EHOSTUNREACH`）。`NetworkPrinter` 已内置回退到系统
   `nc`，改动发送逻辑时别把这个回退删掉。
5. **CUPS 原始队列在 macOS 上已不支持**（`lpadmin -m raw` 被拒），README 里的
   USB 方案在较新系统上走不通。

## Agent skills

### Issue tracker

issue 以 markdown 文件存在 `.scratch/<feature>/`（本地文件，不用 GitHub Issues）。见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用五个默认标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

single-context：根目录 `GLOSSARY.md` + `docs/adr/`。见 `docs/agents/domain.md`。
