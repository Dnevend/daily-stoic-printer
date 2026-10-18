"""排版与编码。"""

from .escpos import encode
from .receipt import render, test_page

__all__ = ["encode", "render", "test_page"]
