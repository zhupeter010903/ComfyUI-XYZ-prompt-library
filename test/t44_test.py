# T44 — job_registry, metadata_sync.queue_many, _read_jobs_active (ComfyUI-free)
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_queue_many_merges_and_wakes_once(monkeypatch):
    from gallery import metadata_sync as ms

    pend: dict = {}
    monkeypatch.setattr(ms, "_pending", pend)
    monkeypatch.setattr(ms, "_notify_lock", threading.Lock())
    wake_calls = []

    def _t():
        class _E:
            def set(self) -> None:
                wake_calls.append(1)
        return _E()

    monkeypatch.setattr(ms, "_wake", _t())
    ms.queue_many({1: 2, 3: 1})
    assert dict(pend) == {1: 2, 3: 1}
    assert len(wake_calls) == 1, wake_calls


def test_job_registry_sync_bulk_list_finish():
    from gallery import job_registry as jr
    from gallery import ws_hub

    try:
        jr.reset_for_test()
        ws_hub.reset_clients()
        d0 = {
            "bulk_id": "abc1",
            "done": 0,
            "total": 3,
            "kind": "favorite",
        }
        b = jr.sync_bulk_payload(d0)
        assert b["job_id"] == "abc1"
        assert len(jr.list_active()) == 1
        jr.sync_bulk_payload({**b, "done": 2, "total": 3, "kind": "favorite"})
        assert jr.list_active()[0]["done"] == 2
        jr.finish_bulk(
            {**b, "done": 3, "total": 3, "kind": "favorite", "failed": []},
        )
        assert jr.list_active() == []
    finally:
        jr.reset_for_test()
        ws_hub.reset_clients()


def test_routes_read_jobs_active():
    from gallery import job_registry as jr, routes

    jr.reset_for_test()
    try:
        assert routes._read_jobs_active() == {"jobs": []}
        jr.start_generic_job(
            "z1", kind="x", done=0, total=0, phase="a", message="b",
        )
        j = routes._read_jobs_active()["jobs"]
        assert len(j) == 1
        assert j[0]["job_id"] == "z1"
    finally:
        jr.reset_for_test()
