"""Rolling audit log for destructive gallery actions + heartbeat stats (T25).

Writes JSON lines to ``<data_dir>/gallery_audit.log`` via
``TimedRotatingFileHandler`` (midnight rotation, 30 backups ≈ 30 days).

Call ``configure(data_dir)`` once from ``gallery.setup`` before any log line.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("xyz.gallery.audit")

__all__ = ["configure", "log_event", "log_heartbeat_stats"]

_file_logger: Optional[logging.Logger] = None


def configure(*, data_dir: Path) -> None:
    """Attach a day-rotating file handler under ``data_dir``."""
    global _file_logger
    if _file_logger is not None:
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "gallery_audit.log"
    h = logging.handlers.TimedRotatingFileHandler(
        filename=str(path),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    h.setFormatter(logging.Formatter("%(message)s"))
    lg = logging.getLogger("xyz.gallery.audit.file")
    lg.handlers.clear()
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    _file_logger = lg


def log_event(
    kind: str,
    actor: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one JSON object line (best-effort; never raises)."""
    if _file_logger is None:
        return
    rec: Dict[str, Any] = {
        "ts": int(time.time()),
        "kind": str(kind),
        "actor": str(actor) if actor else "unknown",
    }
    if payload:
        rec["data"] = dict(payload)
    try:
        _file_logger.info(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        logger.debug("audit log_event failed", exc_info=True)


def log_heartbeat_stats(
    *,
    events_seen: int,
    rows_coalesced: int,
    scans_done: int,
    drifts_found: int,
) -> None:
    log_event(
        "heartbeat_stats",
        "system",
        {
            "events_seen": int(events_seen),
            "coalesced": int(rows_coalesced),
            "scans_done": int(scans_done),
            "drifts_found": int(drifts_found),
        },
    )
