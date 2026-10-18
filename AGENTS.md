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

## Agent skills

### Issue tracker

issue 以 markdown 文件存在 `.scratch/<feature>/`（本地文件，不用 GitHub Issues）。见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用五个默认标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

single-context：根目录 `GLOSSARY.md` + `docs/adr/`。见 `docs/agents/domain.md`。
