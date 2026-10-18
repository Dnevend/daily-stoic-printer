"""把正文翻译成中文。

默认用 MyMemory 免费接口（无需 key；匿名每天 5000 字符，填 ``email`` 可提到 50000），
备用 translate.googleapis.com。译文按段落缓存在 ``data/cache/translate/``，
同一段只翻一次，重跑/离线也能出结果。

翻译是"尽力而为"：失败只记日志并跳过译文，不影响打印正文。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("dailyprint")

UA = "dailyprint/0.1 (+https://github.com/Dnevend/daily-stoic-printer)"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"

MAX_CHUNK = 450  # MyMemory 单次请求约 500 字节上限，留点余量
_BAD_MARKERS = ("MYMEMORY WARNING", "QUERY LENGTH LIMIT", "INVALID", "PLEASE SELECT")
_CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def _join_wrapped(text: str) -> str:
    """把译文里的软换行拼回一行：中英之间留空格，中文之间直接相接。"""
    out = ""
    for line in (ln.strip() for ln in text.split("\n")):
        if not line:
            continue
        if not out:
            out = line
        elif _CJK.search(out[-1]) and _CJK.search(line[0]):
            out += line
        else:
            out += " " + line
    return out


class TranslationError(RuntimeError):
    pass


# ---------------------------------------------------------------- 提供方

def _get_json(url: str, timeout: int) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def mymemory(text: str, target: str, *, timeout: int = 20, email: str = "") -> str:
    params = {"q": text, "langpair": f"en|{target}"}
    if email:
        params["de"] = email
    payload = _get_json(f"{MYMEMORY_URL}?{urllib.parse.urlencode(params)}", timeout)
    out = ((payload or {}).get("responseData") or {}).get("translatedText") or ""
    if not out or any(m in out.upper() for m in _BAD_MARKERS):
        raise TranslationError(f"MyMemory 返回异常: {out[:80]!r}")
    return out


def google_free(text: str, target: str, *, timeout: int = 20, email: str = "") -> str:
    params = {"client": "gtx", "sl": "en", "tl": target, "dt": "t", "q": text}
    payload = _get_json(f"{GOOGLE_URL}?{urllib.parse.urlencode(params)}", timeout)
    segments = payload[0] if payload else []
    out = "".join(seg[0] for seg in segments if seg and seg[0])
    if not out:
        raise TranslationError("Google 返回空结果")
    return out


PROVIDERS: dict[str, Callable[..., str]] = {
    "mymemory": mymemory,
    "google": google_free,
}
DEFAULT_PROVIDERS: tuple[str, ...] = ("mymemory", "google")


# ---------------------------------------------------------------- 切块

def split_chunks(text: str, limit: int = MAX_CHUNK) -> list[str]:
    """按句子边界切块，单块不超过 limit 字符（超长单句硬切）。"""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    chunks: list[str] = []
    cur = ""
    for sentence in sentences:
        if not cur:
            cur = sentence
        elif len(cur) + 1 + len(sentence) <= limit:
            cur = f"{cur} {sentence}"
        else:
            chunks.append(cur)
            cur = sentence
    if cur:
        chunks.append(cur)

    out: list[str] = []
    for chunk in chunks:
        while len(chunk) > limit:
            out.append(chunk[:limit])
            chunk = chunk[limit:]
        if chunk:
            out.append(chunk)
    return out


# ---------------------------------------------------------------- 翻译器

class Translator:
    def __init__(
        self,
        cache_dir: Path,
        *,
        target: str = "zh-CN",
        providers: tuple[str, ...] = DEFAULT_PROVIDERS,
        email: str = "",
        timeout: int = 20,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.target = target
        self.providers = tuple(p for p in providers if p in PROVIDERS) or DEFAULT_PROVIDERS
        self.email = email
        self.timeout = timeout
        self.requests = 0  # 本次实际发出的请求数（用于观察额度）

    # ------------------------------------------------------------ 缓存

    def _cache_path(self, text: str) -> Path:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.txt"

    # ------------------------------------------------------------ 对外

    def translate(self, text: str) -> str:
        """按段落翻译，保留段落结构。"""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return "\n\n".join(self._translate_paragraph(p) for p in paragraphs)

    def _translate_paragraph(self, paragraph: str) -> str:
        cached = self._cache_path(paragraph)
        if cached.exists():
            return _join_wrapped(cached.read_text(encoding="utf-8"))
        translated = "".join(
            _join_wrapped(self._translate_chunk(c)) for c in split_chunks(paragraph)
        ).strip()
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(translated, encoding="utf-8")
        return translated

    def _translate_chunk(self, chunk: str) -> str:
        last_err: Exception | None = None
        for name in self.providers:
            fn = PROVIDERS[name]
            for attempt in range(2):
                try:
                    self.requests += 1
                    return fn(chunk, self.target, timeout=self.timeout, email=self.email)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    log.debug("翻译提供方 %s 失败(第 %d 次): %s", name, attempt + 1, e)
                    time.sleep(0.8 * (attempt + 1))
        raise TranslationError(f"翻译失败（已尝试 {', '.join(self.providers)}）: {last_err}")
