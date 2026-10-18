from dailyprint.enrich.vocab import select_vocab

# 模拟高频词表：前 6 个视为"已认识"
FREQ = [
    "watch",
    "mind",
    "demand",
    "tomorrow",
    "conversation",
    "ourselves",
    "rarely",
    "settle",
    "sphere",
    "continent",
]


def test_skips_inflections_of_common_words():
    text = "He was watching the sphere quietly."
    words = [v.word for v in select_vocab(text, FREQ, known=6, limit=5)]
    assert "watching" not in words  # watch 在已认识列表里
    assert "sphere" in words


def test_skips_proper_nouns_and_contractions():
    text = "Charles Gaulle said we're settling by the continent."
    words = [v.word for v in select_vocab(text, FREQ, known=6, limit=5)]
    assert "charles" not in words
    assert "gaulle" not in words
    assert "we're" not in words


def test_one_word_per_sentence():
    text = "The sphere and the continent are both inaccessible here."
    assert len(select_vocab(text, FREQ, known=6, limit=5)) == 1


def test_prefers_rarer_words_and_returns_article_order():
    text = "We rarely do this. The sphere is big. A continent awaits."
    vocab = select_vocab(text, FREQ, known=6, limit=2)
    # 最稀有的两个（continent、sphere），但输出按文章顺序
    assert [v.word for v in vocab] == ["sphere", "continent"]


def test_respects_limit():
    text = (
        "We rarely do. Please settle in. The sphere is here. "
        "A continent awaits. It is inaccessible."
    )
    assert len(select_vocab(text, FREQ, known=6, limit=2)) == 2


def test_empty_wordlist_means_no_common_filter():
    text = "The sphere is here. An inaccessible cliff looms."
    words = [v.word for v in select_vocab(text, [], known=0, limit=5)]
    assert "inaccessible" in words
