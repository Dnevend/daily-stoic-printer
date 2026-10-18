"""数据模型：来源抓到的文章、生词条目、一期要打印的内容。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Article:
    """一篇待打印的文章。"""

    source: str
    title: str
    url: str
    date: str  # YYYY-MM-DD
    text: str = ""  # 纯文本正文（打印用）
    raw: str = ""  # 原始正文（Markdown/HTML 转换结果，存档用）
    images: list[str] = field(default_factory=list)


@dataclass
class VocabItem:
    """一个生词/短语及其语境和释义。"""

    word: str
    context: str = ""
    gloss: str = ""  # 中文释义


@dataclass
class Issue:
    """一期内容 = 文章 + 生词表。"""

    article: Article
    vocab: list[VocabItem] = field(default_factory=list)
