"""英汉词典（ECDICT 导出的 TSV，由 ``dailyprint build-data`` 生成）。"""

from __future__ import annotations

import re
from pathlib import Path

from ..textutil import lemmas, trim_gloss

# ECDICT 的屈折词条释义形如 "n. errand的复数; ..."，命中时回退到原形
_MESSY = re.compile(r"的(复数|过去式|过去分词|现在分词|第三人称单数|比较级|最高级)")


class Dictionary:
    """懒加载的 word -> 中文释义映射。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._entries: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._entries is not None:
            return self._entries
        entries: dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if "\t" in line:
                    word, gloss = line.split("\t", 1)
                    entries[word] = gloss
        self._entries = entries
        return entries

    def __len__(self) -> int:
        return len(self._load())

    @property
    def available(self) -> bool:
        return self.path.exists()

    def lookup(self, word: str) -> str:
        """查释义；若命中的是屈折词条则回退到原形。"""
        entries = self._load()
        w = word.lower()
        gloss = entries.get(w, "")
        if gloss and not _MESSY.search(gloss):
            return trim_gloss(gloss)
        for cand in sorted(lemmas(w)):
            if cand == w:
                continue
            other = entries.get(cand, "")
            if other and not _MESSY.search(other):
                return trim_gloss(other)
        return trim_gloss(gloss)


def load_dictionary(path: Path | str) -> Dictionary:
    return Dictionary(path)
