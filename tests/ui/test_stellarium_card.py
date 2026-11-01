"""Stellarium card states (H14), offscreen Qt. One test function."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.ui.panels.stellarium_card import StellariumCard  # noqa: E402
from argos.ui.shell import Shell  # noqa: E402


def test_stellarium_card_shows_a_bind_failure_and_the_listening_address() -> None:
    """H14: a port already in use was logged, but the card said "stopped" with
    no reason (and Stellarium GoTos never arrived); the running label named
    the port without the host."""
    app = QApplication.instance() or QApplication(["test"])
    card = StellariumCard(host="127.0.0.1", tcp_port=10001, online_target_lookup=False)
    try:
        error = "bind 127.0.0.1:10001 failed — [Errno 48] Address already in use"
        shell = SimpleNamespace(_connection=SimpleNamespace(stellarium_card=card))
        Shell._on_stellarium_error(shell, error)
        text = card._status_lbl.text()
        assert "failed" in text and "Address already in use" in text
        assert card._server_btn.text() == "▶  Start server"  # can be retried

        card.set_server_state(True)
        assert "127.0.0.1:10001" in card._status_lbl.text()

        card.set_server_state(False)  # a normal stop
        assert card._status_lbl.text() == "○  stopped"
    finally:
        card.deleteLater()
        app.processEvents()
