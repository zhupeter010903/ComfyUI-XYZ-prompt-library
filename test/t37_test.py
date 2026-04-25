"""T37 — detail `metadata.positive_prompt_normalized` (§11 V1.1-F12) + 序列化一致."""

from __future__ import annotations

from gallery.routes import _metadata_positive_prompt_normalized, _prompt_extra_stopwords
from gallery import vocab as _vocab


def test_metadata_positive_prompt_normalized_empty() -> None:
    assert _metadata_positive_prompt_normalized(None) is None
    assert _metadata_positive_prompt_normalized("") is None
    assert _metadata_positive_prompt_normalized("  \n\t") is None


def _expected_join(s: str):
    toks = _vocab.normalize_prompt(s, _prompt_extra_stopwords())
    if not toks:
        return None
    return ", ".join(toks)


def test_metadata_positive_prompt_normalized_joins_vocab_pipeline() -> None:
    s = "a cat on a mat"
    assert _metadata_positive_prompt_normalized(s) == _expected_join(s)


def test_metadata_positive_prompt_normalized_matches_token_join() -> None:
    s = "hello, world, hello"
    assert _metadata_positive_prompt_normalized(s) == _expected_join(s)
