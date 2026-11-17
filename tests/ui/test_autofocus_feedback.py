"""ImagingPage autofocus feedback (S23), on stand-in pages — no widgets.

Stop AF and the focuser card's Halt both land in ``_on_focuser_halt``; the
end of a sweep lands in ``_on_af_done``.
"""

from __future__ import annotations

from types import SimpleNamespace

from argos.ui.pages.imaging_page import ImagingPage


def test_af_result_without_a_best_focus_is_not_reported_as_complete() -> None:
    """S23: best_found(start, None) after a stop or a rejected sweep was
    logged 'Autofocus complete' and the status said 'Focused'."""

    def page():
        logs, actions = [], []
        dock = SimpleNamespace(
            set_position=lambda pos: None,
            vcurve=SimpleNamespace(set_best=lambda pos, hfd: None),
        )
        fake = SimpleNamespace(
            _focuser_dock=dock,
            autofocus_best=SimpleNamespace(emit=lambda pos, hfd: None),
            log_message=SimpleNamespace(emit=lambda level, msg: logs.append((level, msg))),
            action_changed=SimpleNamespace(emit=actions.append),
        )
        return fake, logs, actions

    fake, logs, actions = page()
    ImagingPage._on_af_done(fake, 25_000, None)
    assert not any("complete" in msg for _level, msg in logs), logs
    assert not any("Focused" in text for text in actions), actions
    assert any("25000" in msg for _level, msg in logs), logs

    fake, logs, actions = page()
    ImagingPage._on_af_done(fake, 25_083, 1.7)
    assert ("OK", "Autofocus complete — best pos=25083  HFD=1.7") in logs


def test_halt_during_autofocus_does_not_stop_the_return_move() -> None:
    """S23: Stop AF and Halt share ImagingPage._on_focuser_halt; while AF
    runs it must stop the sweep only, not halt the focuser's return."""
    calls: list[str] = []
    engine = SimpleNamespace(
        autofocus_running=True,
        stop_autofocus=lambda: calls.append("stop_autofocus"),
    )
    session = SimpleNamespace(focuser=object(), focuser_halt=lambda: calls.append("halt"))
    ImagingPage._on_focuser_halt(SimpleNamespace(_engine=engine, _session=session))
    assert calls == ["stop_autofocus"]

    calls.clear()
    engine.autofocus_running = False  # a plain Halt still halts the focuser
    ImagingPage._on_focuser_halt(SimpleNamespace(_engine=engine, _session=session))
    assert calls[-1] == "halt"
