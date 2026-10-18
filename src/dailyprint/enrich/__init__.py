"""生词挑选、词典查询、推广段过滤与翻译。"""

from .dictionary import Dictionary, load_dictionary
from .promo import strip_promo_paragraphs
from .translate import TranslationError, Translator
from .vocab import select_vocab

__all__ = [
    "Dictionary",
    "TranslationError",
    "Translator",
    "load_dictionary",
    "select_vocab",
    "strip_promo_paragraphs",
]
