"""数据模型：来源抓到的文章、生词条目、一期要打印的内容。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
class ImageRef:
    """正文配图：远程 URL + 显示名（本地文件路径在下载后填入）。"""

    url: str
    label: str
    path: Path | None = None


@dataclass
class Cover:
    """封面图（从外部图源取），可带署名行。"""

    image: ImageRef
    credit: str = ""


@dataclass
class Issue:
    """一期内容 = 文章 + 封面 + 配图 + 译文 + 生词表。"""

    article: Article
    vocab: list[VocabItem] = field(default_factory=list)
    translation: str = ""  # 正文的中文译文（可选）
    images: list[ImageRef] = field(default_factory=list)  # 要打印的正文配图
    cover: Cover | None = None  # 封面图（可选）

    def all_images(self) -> list[ImageRef]:
        """封面 + 正文配图，按打印顺序。"""
        items = [self.cover.image] if self.cover else []
        return [*items, *self.images]
