from pathlib import Path

import pytest

from dailyprint.enrich.dictionary import Dictionary


@pytest.fixture
def dictionary(tmp_path: Path) -> Dictionary:
    path = tmp_path / "dict.tsv"
    path.write_text(
        "errand\tn. 差使, 差事\nerrands\tn. errand的复数; 差使\nsphere\tn. 球, 球体, 范围\n",
        encoding="utf-8",
    )
    return Dictionary(path)


def test_lookup_exact(dictionary: Dictionary):
    assert dictionary.lookup("sphere") == "n. 球, 球体, 范围"


def test_lookup_is_case_insensitive(dictionary: Dictionary):
    assert dictionary.lookup("Sphere") == "n. 球, 球体, 范围"


def test_lookup_falls_back_to_lemma_for_inflected_entries(dictionary: Dictionary):
    # "errands" 的词条释义很啰嗦，应回退到原形 "errand" 的干净释义
    assert dictionary.lookup("errands") == "n. 差使, 差事"


def test_lookup_missing_returns_empty(dictionary: Dictionary):
    assert dictionary.lookup("nonexistentword") == ""


def test_unavailable_when_file_missing(tmp_path: Path):
    assert Dictionary(tmp_path / "nope.tsv").available is False
    assert len(Dictionary(tmp_path / "nope.tsv")) == 0
