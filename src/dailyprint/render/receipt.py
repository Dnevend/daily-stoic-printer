"""80mm 小票排版（纯文本，不含 ESC/POS 控制码）。"""

from __future__ import annotations

from ..models import Issue
from ..textutil import WIDTH, center_disp, to_ascii, wrap_disp


def render(issue: Issue, *, width: int = WIDTH, stamp: str = "") -> str:
    """把一期内容排成 80mm 小票文本。"""
    article = issue.article
    lines: list[str] = []

    lines.append("=" * width)
    lines.append(center_disp("DAILY PRINT", width))
    lines.append(center_disp(article.date, width))
    lines.append("=" * width)
    lines.append("")
    for ln in wrap_disp(to_ascii(article.title), width):
        lines.append(center_disp(ln, width))
    lines.append("")
    lines.append("-" * width)
    lines.append("")
    lines.extend(wrap_disp(article.text, width))

    if issue.vocab:
        lines.append("")
        lines.append("-" * width)
        lines.append("TODAY'S WORDS")
        lines.append("-" * width)
        for i, item in enumerate(issue.vocab, 1):
            lines.append(f"{i}. {item.word}")
            if item.gloss:
                for ln in wrap_disp(item.gloss, width - 3):
                    lines.append("   " + ln)
            for ln in wrap_disp(item.context, width - 3):
                lines.append("   " + ln)
            lines.append("")

    lines.append("-" * width)
    lines.extend(wrap_disp(f"source: {article.url}", width))
    if stamp:
        lines.append(f"printed: {stamp}")
    lines.append("=" * width)
    return "\n".join(lines)


def test_page(width: int = WIDTH) -> str:
    return "\n".join(
        [
            "=" * width,
            center_disp("PRINTER TEST PAGE", width),
            "=" * width,
            "",
            "If you can read this, printing works.",
            "",
            "0123456789" * 4,
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "abcdefghijklmnopqrstuvwxyz",
            "",
            "ABC 中文测试：热敏打印正常 / 中文模式正常",
            "Mixed 中英 mixed 一行 width test 12345",
            "",
            f"width = {width} columns",
            "chars: ' \" - -- ... * @#$%&()",
            "",
            "=" * width,
        ]
    )
