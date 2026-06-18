"""Level 2 — Validate native TCP client (port 4700).

Requires the real Seestar S30 Pro OR the seestar_alp simulator.

seestar_alp simulator:
  git clone https://github.com/smart-underworld/seestar_alp
  cd seestar_alp && pip install -r requirements.txt
  python simulator/src/main.py   (listens on localhost:4700)

Usage:
    # Real Seestar
    .venv/bin/python scripts/validate_native.py 192.168.1.X

    # seestar_alp simulator
    .venv/bin/python scripts/validate_native.py localhost
    .venv/bin/python scripts/validate_native.py localhost 14700  # test port
"""

import sys
import time

HOLD_SECONDS = 2  # how long to hold each jog direction


def section(title: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 4700

    print(f"\nArgos — Native TCP validation  ({host}:{port})")
    print("  WARNING: If using real Seestar, the mount will physically move!")
    print("  Make sure the arm is deployed and the sky is clear.\n")

    from argos.core.seestar.native_client import (
        SeestarNativeClient, SeestarNativeError,
        ANGLE_NORTH, ANGLE_SOUTH, ANGLE_EAST, ANGLE_WEST,
        SPEED_SLOW, SPEED_NORMAL,
    )

    # ── 1. Connection ─────────────────────────────────────────────────────
    section("1. TCP Connection")
    client = SeestarNativeClient(host=host, port=port)
    try:
        client.connect()
        print(f"  OK   Connected  firmware_ver_int={client.firmware_ver_int}")
        print(f"       needs_verify={client._needs_verify()}")
    except SeestarNativeError as exc:
        print(f"  FAIL Cannot connect: {exc}")
        print("       Check: is Seestar on? Same WiFi? Or is simulator running?")
        sys.exit(1)

    # ── 2. Master CLI claim ───────────────────────────────────────────────
    section("2. Master CLI (already done at connect)")
    print("  INFO set_setting(master_cli=True) is sent automatically at connect.")
    print("       If you see this without error, master CLI was claimed.")
    print(f"  OK   is_connected={client.is_connected}")

    # ── 3. Jogging ────────────────────────────────────────────────────────
    section("3. Manual jogging (scope_speed_move)")

    directions = [
        ("North", ANGLE_NORTH),
        ("East",  ANGLE_EAST),
        ("South", ANGLE_SOUTH),
        ("West",  ANGLE_WEST),
    ]

    for name, angle in directions:
        print(f"  ...  Moving {name} at SLOW speed for {HOLD_SECONDS}s…")
        try:
            client.move(angle=angle, speed=SPEED_SLOW, dur_sec=HOLD_SECONDS)
            time.sleep(HOLD_SECONDS + 0.5)  # wait for move to complete
            print(f"  OK   {name} move sent and acknowledged")
        except SeestarNativeError as exc:
            print(f"  FAIL {name} move: {exc}")

    # ── 4. Stop ───────────────────────────────────────────────────────────
    section("4. Stop (iscope_stop_view)")
    try:
        client.stop()
        print("  OK   Stop sent")
    except SeestarNativeError as exc:
        print(f"  FAIL Stop: {exc}")

    # ── 5. Disconnect ─────────────────────────────────────────────────────
    section("5. Disconnect")
    client.disconnect()
    print(f"  OK   Disconnected  is_connected={client.is_connected}")

    print(f"\n{'═' * 55}")
    print("  Native validation complete.")
    print("  Check the logs above — every direction should show OK.")
    print(f"{'═' * 55}\n")


if __name__ == "__main__":
    main()
