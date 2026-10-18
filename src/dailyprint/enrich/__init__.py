"""生词挑选与词典查询。"""

from .dictionary import Dictionary, load_dictionary
from .vocab import select_vocab

__all__ = ["Dictionary", "load_dictionary", "select_vocab"]
