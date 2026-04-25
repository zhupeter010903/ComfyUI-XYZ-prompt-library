"""XYZ Image Gallery — prompt / tag normalisation (T15).

Pure string transforms only: no SQLite, no HTTP, no repo imports
(PROJECT_SPEC §8.8, AI_RULES R5.5).
"""

from __future__ import annotations

import re
from typing import FrozenSet, List, Optional, Tuple

__all__ = [
    "normalize_prompt",
    "normalize_tag",
    "normalize_stored_model",
    "split_positive_prompt_words",
    "PROMPT_VOCAB_PIPELINE_VERSION",
]

# Bumped when §8.8 prompt-token semantics change (T30 v1.1: step 4 removed).
PROMPT_VOCAB_PIPELINE_VERSION: int = 2

_RE_LORA = re.compile(r"<(?:lora|lyco|hypernet)\s*:[^>]+>", re.IGNORECASE)
_RE_KEYWORD = re.compile(r"\b(break|and|addcomm|addbase)\b")
_RE_WEIGHTED = re.compile(
    r"[\(\[\{]\s*([^\(\)\[\]\{\}:]+?)\s*(?P<wt>:\s*-?\d*\.?\d+)?\s*[\)\]\}]"
)


def _unwrap_weighted_block(m: re.Match) -> str:
    inner = m.group(1) or ""
    wt = m.group("wt")
    if wt:
        return inner
    if re.search(r"\s", inner):
        return m.group(0)
    return inner
_RE_SPLIT = re.compile(r"[,\|]+")
_RE_WS = re.compile(r"\s+")
_RE_TRIM = re.compile(r"^[\.,;:!\?\-_]+|[\.,;:!\?\-_]+$")
_RE_NUM_ONLY = re.compile(r"^\d+(?:\.\d+)?$")


def _strip_trailing_ascii_periods(s: str) -> str:
    """Strip trailing U+002E full stops (phrase + word vocab storage)."""
    return str(s).rstrip(".")
# §11 F04 word-mode lexemes: commas and ASCII whitespace split the prompt
# string (after F05 underscore→space). Same rule applies to wire blobs
# built from repeated ``prompt`` / ``positive_tokens`` fragments.
_RE_WORD_LEXEMES = re.compile(r"[,\s]+")

# SD-style escaped literal parens must survive weight-unwrap (§11 / T30).
_ESC_LP_SENT = "\ue000"
_ESC_RP_SENT = "\ue001"


def _shield_escaped_parens(s: str) -> str:
    parts: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n and s[i + 1] in "()":
            parts.append(_ESC_LP_SENT if s[i + 1] == "(" else _ESC_RP_SENT)
            i += 2
        else:
            parts.append(s[i])
            i += 1
    return "".join(parts)


def _unshield_escaped_parens(s: str) -> str:
    return s.replace(_ESC_LP_SENT, "(").replace(_ESC_RP_SENT, ")")


# Canonical ``image.model`` in SQLite: strip common weight-file extensions so
# ``foo.safetensors`` and ``foo`` converge (T21 follow-up).
_MODEL_FILE_EXT_RE = re.compile(
    r"\.(safetensors|ckpt|pt|pth|bin|sft|gguf|onnx|mlmodel|zip)$",
    re.IGNORECASE,
)


def normalize_stored_model(text: Optional[str]) -> Optional[str]:
    """Return canonical model name for DB storage, or ``None`` if empty."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    s2 = _MODEL_FILE_EXT_RE.sub("", s).strip()
    return s2 if s2 else None


_DEFAULT_STOP: FrozenSet[str] = frozenset({
    "a", "an", "the", "of", "and", "or", "with", "in", "on", "for",
    "to", "by", "at", "is", "as",
})


def normalize_prompt(
    text: Optional[str],
    extra_stopwords: FrozenSet[str] = frozenset(),
) -> List[str]:
    """§8.8 pipeline: return ordered unique tokens for one positive prompt."""
    if not text:
        return []
    s = text.lower()
    s = _shield_escaped_parens(s)

    s = _RE_LORA.sub(" ", s)
    s = _RE_KEYWORD.sub(" ", s)
    for _ in range(8):
        new_s = _RE_WEIGHTED.sub(_unwrap_weighted_block, s)
        if new_s == s:
            break
        s = new_s

    raw_tokens = _RE_SPLIT.split(s)

    stopwords = _DEFAULT_STOP | extra_stopwords
    out: List[str] = []
    seen: set[str] = set()
    for t in raw_tokens:
        t = _RE_WS.sub(" ", t).strip()
        t = _RE_TRIM.sub("", t).strip()
        t = _unshield_escaped_parens(t)
        t = _strip_trailing_ascii_periods(t)
        if not t or len(t) == 1 or len(t) > 64:
            continue
        if _RE_NUM_ONLY.match(t):
            continue
        if t in stopwords:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def normalize_tag(text: Optional[str]) -> str:
    """Reuse §8.8 with an empty stopword set; collapse to one display string."""
    parts = normalize_prompt(text, frozenset())
    return " ".join(parts)


def split_positive_prompt_words(raw: Optional[str]) -> Tuple[str, ...]:
    """§11 F04 *word* mode — lexemes for ``word_token`` / ``image_word_token``.

    Pipeline: ``None``/blank → empty; else apply §11 F05 ``_``→space on the
    whole string, then split on commas and runs of ASCII whitespace; each
    piece is lower-cased; order preserved, duplicates dropped (first wins).
    """
    if raw is None:
        return ()
    s0 = str(raw).strip()
    if not s0:
        return ()
    s = s0.replace("_", " ")
    out: List[str] = []
    seen: set[str] = set()
    for piece in _RE_WORD_LEXEMES.split(s):
        t = _strip_trailing_ascii_periods(piece.strip())
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return tuple(out)
