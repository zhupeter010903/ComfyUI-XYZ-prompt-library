"""XYZ Image Gallery — prompt / tag normalisation (T15).

Pure string transforms only: no SQLite, no HTTP, no repo imports
(PROJECT_SPEC §8.8, AI_RULES R5.5).
"""

from __future__ import annotations

import re
from typing import FrozenSet, List, Optional

__all__ = [
    "normalize_prompt",
    "normalize_tag",
    "normalize_stored_model",
]

_RE_LORA = re.compile(r"<(?:lora|lyco|hypernet)\s*:[^>]+>", re.IGNORECASE)
_RE_KEYWORD = re.compile(r"\b(break|and|addcomm|addbase)\b")
_RE_WEIGHTED = re.compile(
    r"[\(\[\{]\s*([^\(\)\[\]\{\}:]+?)\s*(?::\s*-?\d*\.?\d+)?\s*[\)\]\}]"
)
_RE_PUNCT = re.compile(r"[\(\)\[\]\{\}\\]")
_RE_SPLIT = re.compile(r"[,\|]+")
_RE_WS = re.compile(r"\s+")
_RE_TRIM = re.compile(r"^[\.,;:!\?\-_]+|[\.,;:!\?\-_]+$")
_RE_NUM_ONLY = re.compile(r"^\d+(?:\.\d+)?$")

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

    s = _RE_LORA.sub(" ", s)
    s = _RE_KEYWORD.sub(" ", s)
    for _ in range(8):
        new_s = _RE_WEIGHTED.sub(r"\1", s)
        if new_s == s:
            break
        s = new_s
    s = _RE_PUNCT.sub(" ", s)

    raw_tokens = _RE_SPLIT.split(s)

    stopwords = _DEFAULT_STOP | extra_stopwords
    out: List[str] = []
    seen: set[str] = set()
    for t in raw_tokens:
        t = _RE_WS.sub(" ", t).strip()
        t = _RE_TRIM.sub("", t).strip()
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
