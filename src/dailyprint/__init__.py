"""dailyprint —— 把每日英文文章排成 80mm 热敏小票打印。

模块划分：
    sources/   内容来源（Daily Stoic、通用 RSS……），返回 Article
    enrich/    生词挑选与词典查询（中文释义）
    render/    80mm 排版与 ESC/POS 编码
    printers/  发送到打印机（网络 9100 / CUPS）
"""

__version__ = "0.1.0"
