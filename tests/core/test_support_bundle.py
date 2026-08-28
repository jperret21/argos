"""Tests for private, explicit field-support artifacts (no network involved)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from argos.core.support_bundle import create_support_bundle, redact_text, write_crash_report


def test_log_redaction_removes_ip_and_home_path(tmp_path: Path) -> None:
    text = f"connected to 10.0.0.1 from {tmp_path}/sessions"
    redacted = redact_text(text, home=tmp_path)
    assert "10.0.0.1" not in redacted
    assert str(tmp_path) not in redacted
    assert "<redacted-ip>" in redacted
    assert "~/sessions" in redacted


def test_support_bundle_whitelists_session_metadata_and_redacts_logs(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "argos.log").write_text(f"connected 192.168.4.1 at {tmp_path}\n", encoding="utf-8")
    session = tmp_path / "session"
    diagnostics = session / "diagnostics"
    diagnostics.mkdir(parents=True)
    (session / "session.json").write_text(
        '{"observer":"Jules", "latitude":37.8, "frames": []}', encoding="utf-8"
    )
    (session / "photometry.csv").write_text("jd,ra_deg,mag\n1,300.1,12.2\n", encoding="utf-8")
    (diagnostics / "run.jsonl").write_text(
        '{"kind":"frame", "dec_deg":22.7}\n', encoding="utf-8"
    )
    (session / "raw.fits").write_bytes(b"must not be shared")
    (session / "private.bin").write_bytes(b"must not be shared")

    result = create_support_bundle(
        tmp_path / "report.zip",
        log_directory=logs,
        session_directory=session,
        config_summary={"hardware_profile": "s30pro"},
        home=tmp_path,
    )

    assert result.path.exists()
    with zipfile.ZipFile(result.path) as archive:
        names = set(archive.namelist())
        assert {"README.txt", "manifest.json", "logs/argos.log"} <= names
        assert "session/session.json" in names
        assert "session/photometry.csv" in names
        assert "session/diagnostics/run.jsonl" in names
        assert not any(name.endswith(".fits") or name.endswith(".bin") for name in names)
        assert "192.168.4.1" not in archive.read("logs/argos.log").decode()
        assert "Jules" not in archive.read("session/session.json").decode()
        assert "300.1" not in archive.read("session/photometry.csv").decode()
        assert "22.7" not in archive.read("session/diagnostics/run.jsonl").decode()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["privacy"]["uploaded_by_argos"] is False
        assert manifest["configuration"] == {"hardware_profile": "s30pro"}


def test_crash_report_is_local_and_contains_traceback(tmp_path: Path) -> None:
    try:
        raise RuntimeError("simulated field failure")
    except RuntimeError as exc:
        report = write_crash_report(type(exc), exc, exc.__traceback__, tmp_path)

    assert report is not None and report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Argos" in text
    assert "simulated field failure" in text
