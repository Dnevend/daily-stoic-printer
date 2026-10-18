"""生词挑选、词典查询与推广段过滤。"""

from .dictionary import Dictionary, load_dictionary
from .promo import strip_promo_paragraphs
from .vocab import select_vocab

__all__ = ["Dictionary", "load_dictionary", "select_vocab", "strip_promo_paragraphs"]
