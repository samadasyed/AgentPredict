"""
Unit tests for the research flight recorder — pure filesystem, no external deps.
"""

from __future__ import annotations

import json

from agents.shared.flight_recorder import FlightRecorder


def test_disabled_by_default_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_CAPTURE", raising=False)
    monkeypatch.setenv("RESEARCH_CAPTURE_DIR", str(tmp_path))
    rec = FlightRecorder("test")
    rec.record("poll", {"a": 1})
    assert not rec.enabled
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_enabled_writes_valid_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_CAPTURE", "1")
    monkeypatch.setenv("RESEARCH_CAPTURE_DIR", str(tmp_path))
    rec = FlightRecorder("test")
    rec.record("poll", {"a": 1})
    rec.record("cycle", {"b": "two"})

    files = list(tmp_path.rglob("test.jsonl"))
    assert len(files) == 1
    lines = [json.loads(l) for l in files[0].read_text().splitlines()]
    assert [l["kind"] for l in lines] == ["poll", "cycle"]
    assert lines[0]["a"] == 1 and lines[1]["b"] == "two"
    assert all(isinstance(l["ts_ms"], int) for l in lines)


def test_non_serializable_payload_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_CAPTURE", "1")
    monkeypatch.setenv("RESEARCH_CAPTURE_DIR", str(tmp_path))
    rec = FlightRecorder("test")
    rec.record("weird", {"obj": object()})  # default=str stringifies it
    line = json.loads(next(tmp_path.rglob("test.jsonl")).read_text())
    assert "object object" in line["obj"]


def test_write_failure_is_swallowed(tmp_path, monkeypatch):
    # Point the capture dir at a FILE — mkdir will fail. Must not raise.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("RESEARCH_CAPTURE", "1")
    monkeypatch.setenv("RESEARCH_CAPTURE_DIR", str(blocker))
    rec = FlightRecorder("test")
    rec.record("poll", {"a": 1})
    rec.record("poll", {"a": 2})  # second write exercises the warned-once path
