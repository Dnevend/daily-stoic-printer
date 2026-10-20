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

- 绝不提交：`articles/`、`prints/`、`logs/`、`data/*.csv`、`data/*.tsv`、`config.toml`、`.venv/`
- 抓取的正文是第三方内容，个人学习用途，不入库
- 提交前跑 `make test` 和 `make lint`

## 已知限制（真机联调得出，改代码前先看）

目标机型是 **XPrinter XP-80T**（80mm、ESC/POS、网口 9100）。实测问题：

1. **位图不可靠**：同一张 576×200 位图单独发能印出清晰照片，夹在完整文章里
   却印成噪点，而命令字节数和后续文字都正常。原因未查明，生产配置因此
   关掉图片（`images = "off"`、`cover.source = "none"`）。**不要默认把图片打开**，
   除非换了机型或在真机上验证过。
2. **位图必须单条命令**：`image_to_raster()` 要一次发完整张图；切成多条
   `GS v 0` 连续下发，从第二条起就乱码。
3. **GS v 0 命令头**必须是 `1D 56 30 00`（`GS v 0 m`），顺序写反会把整段位图当文本打。
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
