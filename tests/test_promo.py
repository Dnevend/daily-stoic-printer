from dailyprint.enrich.promo import promo_reason, strip_promo_paragraphs

# 正文段：引用书籍时也会链到商店，但这是正文，不能删
CONTENT_WITH_LINK = (
    "Ten years ago today, we published a book called "
    "*[The Daily Stoic](https://store.dailystoic.com/pages/x)*. The idea was simple: "
    "366 short Stoic meditations, one for every day of the year."
)
CTA_LINE = "**[Order The Daily Stoic 10th Anniversary Edition](https://store.dailystoic.com/pages/x)**"
MEDALLION_PITCH = (
    "*Our [Memento Mori Medallion](https://store.dailystoic.com/collections/coins/products/"
    "memento-mori) is a touchstone to remind you that you could leave life right now.*"
)
STORE_PITCH = (
    "***Get your Daily Stoic ***[Memento Mori Medallion](https://x/m)* ****at the Daily Stoic "
    "Store, and check out our other Memento Mori reminders in the ***[Collection](https://x/c)***.***"
)
SHORT_CONTENT = "It might be important to you. Life doesn't care."
IMAGE_ONLY = "[![](images/x.jpg)](https://store.dailystoic.com/pages/x)"


def test_content_paragraph_with_store_link_is_kept():
    assert promo_reason(CONTENT_WITH_LINK) is None


def test_short_content_without_link_is_kept():
    assert promo_reason(SHORT_CONTENT) is None


def test_cta_line_is_dropped():
    assert promo_reason(CTA_LINE) == "cta-line"


def test_medallion_pitch_is_dropped():
    assert promo_reason(MEDALLION_PITCH) == "weak-phrase"


def test_weak_phrase_in_long_paragraph_is_kept():
    # 正文里提到 "medallion"/"painted porch" 的长段落不能删
    long_content = (
        "A small group used to gather to hear Zeno teach on the painted porch, and over the "
        "centuries the ideas traveled far beyond that colonnade, finding new readers in every "
        "generation who picked up the book, marked it up, and carried it with them."
    )
    assert promo_reason(long_content) is None


def test_weak_phrase_without_link_is_kept():
    # 描述新版装帧的正文段（无链接）不能删
    content = (
        "There's the new hardcover edition, including signed and individually numbered copies. "
        "And for people who want something a little more special, we've also made a limited "
        "leatherbound version."
    )
    assert promo_reason(content) is None


def test_store_pitch_is_dropped():
    assert promo_reason(STORE_PITCH, cta_words=25) is not None


def test_image_only_paragraph_is_dropped():
    assert promo_reason(IMAGE_ONLY) == "image-only"


def test_strip_keeps_content_and_reports_reasons():
    md = "\n\n".join([CONTENT_WITH_LINK, CTA_LINE, MEDALLION_PITCH, SHORT_CONTENT])
    out, dropped = strip_promo_paragraphs(md)
    assert CONTENT_WITH_LINK in out
    assert SHORT_CONTENT in out
    assert CTA_LINE not in out
    assert MEDALLION_PITCH not in out
    assert len(dropped) == 2
    assert {reason for reason, _ in dropped} == {"cta-line", "weak-phrase"}


def test_extra_phrases_from_config():
    md = "Check out my special offer today, it ends soon."
    out, dropped = strip_promo_paragraphs(md, extra_phrases=("special offer",))
    assert out == ""
    assert dropped[0][0] == "extra:special offer"
