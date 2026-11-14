"""Wave 6b: the attention rules (``argos/server/attention.py``).

Two halves:

- **The lab oracle.** ``web/src/lab/workspace/model/rules.ts`` and its tests
  (``rules.test.ts``) are the reference. :func:`build_night` is a line-by-line
  port of the lab's seeded synthetic night (``night.ts`` ``buildNight``, the
  ``prng`` of ``field.ts``); the pinned values below (frame 150, "HFD 16.0 px =
  2.5× the first 20 frames", the 40-frame silence limit 111.405 s) are what
  the lab's TypeScript prints for the same seed (run once with node), so the
  port and the rules are both checked against it.
- **The service.** Rules evaluated per frame from the published events,
  hysteresis, one item per cause, reopen, acknowledgement by any client, the
  snapshot a client joining mid-run receives, the run's end, the thresholds
  as config keys, and the evaluation cost.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import pytest

from argos.server.attention import NightRules, Signal, Sub, Thresholds
from tests.server.conftest import AUTH, TOKEN, log_messages, receive_until, wait_for

# ---------------------------------------------------------------------------
# The lab's synthetic night (night.ts, field.ts), ported
# ---------------------------------------------------------------------------

_M32 = 0xFFFFFFFF
RUN_START = datetime(2026, 9, 25, 20, 4, 53, tzinfo=timezone.utc).timestamp()
FOCUS_LOSS_FRAME = 148  # night.ts:56


def _imul(a: int, b: int) -> int:
    return (a * b) & _M32


def prng(seed: int):
    """``prng`` of field.ts:42-51 (mulberry32), on unsigned 32-bit values."""
    state = seed & _M32

    def rand() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & _M32
        t = state
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & _M32
        return ((t ^ (t >> 14)) & _M32) / 4294967296

    return rand


def _gauss(rand) -> float:
    u = 0.0
    while u == 0.0:
        u = rand()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * rand())


def _js_round(x: float) -> int:
    return math.floor(x + 0.5)


def build_night(seed: int = 25) -> list[dict]:
    """``buildNight`` of night.ts:58-98 (same draws, same order)."""
    rand = prng(seed)
    out: list[dict] = []
    t = RUN_START + 10 / 2
    span = 169.3 * 60
    for n in range(1, 196):
        if n > 1:
            t += 74.6 if n == 88 else 51.5 + 0.8 * _gauss(rand)
        hours = (t - RUN_START) / 3600
        lost = n >= FOCUS_LOSS_FRAME
        if lost:
            hfd = 16.6 + 0.012 * (n - FOCUS_LOSS_FRAME) + 0.7 * _gauss(rand)
        else:
            hfd = 6.25 + 0.22 * math.sin(n / 23) + 0.16 * _gauss(rand)
        stars = _js_round((2460 if lost else 2982) + (120 if lost else 105) * _gauss(rand))
        _sky = 1180 + 6 * math.sin(n / 31) + 3 * _gauss(rand)
        t_err = 0.035 if lost else 0.012
        c_err = 0.03 if lost else 0.011
        _frac = min(1, (t - RUN_START) / span)
        r = rand()
        comps = 5 if r < 0.55 else 4 if r < 0.85 else 3
        if lost and r > 0.96 and (out[-1]["comps"] if out else None) != 2:
            comps = 2
        _target = 7.36 + 0.12 * hours + t_err * _gauss(rand)
        _target_err = t_err * (0.9 + 0.2 * rand())
        _check = 8.62 + c_err * _gauss(rand)
        _check_err = c_err * (0.9 + 0.2 * rand())
        out.append({"n": n, "t": t, "hfd": hfd, "stars": stars, "comps": comps})
    return out


NIGHT = build_night()


def replay(records, rules: NightRules | None = None) -> tuple[NightRules, list[Signal]]:
    """Feed the frames one by one, as the server does per saved sub."""
    rules = rules or NightRules()
    fired: list[Signal] = []
    for r in records:
        fired += rules.add_sub(Sub(n=r["n"], t=r["t"], hfd=r["hfd"], stars=r["stars"], filter="IR"))
        fired += rules.add_measured(r["comps"], r["n"], r["t"])
    return rules, fired


# -- rules.test.ts, "synthetic night" ------------------------------------------------


def test_the_port_reproduces_the_lab_night():
    assert len(NIGHT) == 195
    rules, _ = replay(NIGHT)
    assert 51 < rules.median_cadence() < 52
    # Pinned from the lab's TypeScript (node, seed 25): frame 150 of buildNight().
    assert NIGHT[149]["hfd"] == pytest.approx(15.972534707836568, abs=1e-9)
    assert NIGHT[149]["stars"] == 2557 and NIGHT[149]["comps"] == 5
    assert NIGHT[149]["t"] == pytest.approx(1790374412.6525497, abs=1e-6)


def test_never_two_frames_with_fewer_than_3_comparisons_before_the_loss():
    streak = 0
    for r in NIGHT[: FOCUS_LOSS_FRAME - 1]:
        streak = streak + 1 if r["comps"] < 3 else 0
        assert streak < 2


# -- rules.test.ts, "attention rules" -------------------------------------------------


def test_the_hfd_rule_fires_on_the_third_bad_frame_after_the_focus_loss():
    _, fired = replay(NIGHT)
    hfd = [s for s in fired if s.rule == "hfd_rise"]
    assert len(hfd) == 1 and hfd[0].on  # one item for the whole loss (hysteresis)
    assert hfd[0].frame == FOCUS_LOSS_FRAME + 2 == 150
    # The lab's own title for that frame (rules.ts:99).
    assert hfd[0].title == "HFD 16.0 px = 2.5× the first 20 frames"
    assert hfd[0].short == "HFD 16.0 px · 2.5× baseline"
    assert hfd[0].since == pytest.approx(NIGHT[149]["t"])


def test_no_hfd_item_before_the_loss():
    _, fired = replay(NIGHT[: FOCUS_LOSS_FRAME + 1])
    assert not [s for s in fired if s.rule == "hfd_rise"]


def test_no_star_count_or_comparison_alarm_on_this_night():
    _, fired = replay(NIGHT)
    assert not [s for s in fired if s.rule in ("star_drop", "comps_low")]


def test_silence_only_past_the_limit_and_only_while_running():
    rules, _ = replay(NIGHT[:40])
    limit = rules.silence_limit()
    assert limit > 110
    assert limit == pytest.approx(111.40484809875488, abs=1e-6)  # the lab's silenceLimit
    last = NIGHT[39]["t"]
    assert rules.silence(last + limit - 1, True, last) == []
    on = rules.silence(last + limit + 1, True, last)
    assert len(on) == 1 and on[0].rule == "no_frame" and on[0].on
    assert on[0].since == pytest.approx(last + limit)
    assert rules.silence(last + limit + 5, True, last) == []  # one item, not one per tick
    rules2, _ = replay(NIGHT[:40])
    assert rules2.silence(last + limit + 1, False, last) == []  # paused: not a silence


def test_the_longest_real_gap_is_no_false_alarm():
    # night.ts: frame 88 comes 74.6 s after 87 (the real run's longest gap).
    rules, _ = replay(NIGHT[:87])
    last = NIGHT[86]["t"]
    assert rules.silence(last + 74.6, True, last) == []


def test_before_two_subs_the_cadence_is_at_least_the_first_subs_own_time():
    """RR Lyr 2026-09-25: sub 1 took 44.5 s from its start to its file (10 s exposure, the
    Seestar's download) and sub 2 started 74.6 s after it. A 13 s planned cadence alone
    would give a 73 s limit: a false critical alarm at the start of the owner's run.
    Before two saves the limit is 2 × floor + 60 s (the science review: the first
    interval also carries the next sub's start-to-save time)."""
    rules = NightRules()
    rules.add_sub(Sub(n=1, t=RUN_START, hfd=10.8, stars=3181, filter="IR", saved=RUN_START + 44.5))
    assert rules.silence_limit(planned=13.0) == pytest.approx(86.0)  # the plan alone
    rules.sub_cost = 44.5
    assert rules.silence_limit(planned=13.0) == pytest.approx(149.0)
    saved = RUN_START + 44.5
    assert rules.silence(saved + 112.3, True, saved, planned=13.0) == []
    (on,) = rules.silence(saved + 150.0, True, saved, planned=13.0)
    assert on.rule == "no_frame" and "cadence 44.5 s + 60 s (before two frames)" in on.detail
    assert "Last frame #1 saved at 20:05:37 UTC" in on.detail
    rules.add_sub(
        Sub(n=2, t=RUN_START + 74.6, hfd=11.0, stars=3203, filter="IR", saved=RUN_START + 119.1)
    )
    assert rules.silence_limit(planned=13.0) == pytest.approx(149.2)  # the median from now


def test_the_service_reads_the_subs_start_to_save_time(night):
    night.start()
    night.publish(
        "frame_saved",
        {"source": "sequence", "frame_type": "light", "filter": "IR", "date_obs": iso(RUN_START),
         "t": iso(RUN_START + 44.5), "frame_seq": 9001, "path": "/nonexistent/sub.fit",
         "record": {"hfd": 10.8, "star_count": 3181}},
    )  # fmt: skip
    night.clock.t = RUN_START + 80.0  # past 73 s (the plan alone), short of 104.5 s
    time.sleep(1.3)  # one tick of the timer
    assert "no_frame" not in active_rules(night.settle())
    assert night.att._run.rules.sub_cost == pytest.approx(44.5)


# -- hysteresis and the other rules ----------------------------------------------------


def _subs(values, start_n=1, key="hfd", filter_name="IR", t0=RUN_START):
    out = []
    for i, v in enumerate(values):
        n = start_n + i
        out.append(
            Sub(
                n=n,
                t=t0 + 50.0 * n,
                hfd=v if key == "hfd" else 6.0,
                stars=v if key == "stars" else 3000,
                filter=filter_name,
            )
        )
    return out


def feed(rules: NightRules, subs) -> list[Signal]:
    fired: list[Signal] = []
    for s in subs:
        fired += rules.add_sub(s)
    return fired


def test_one_bad_frame_never_fires_and_one_good_frame_never_clears():
    rules = NightRules()
    fired = feed(rules, _subs([6.0] * 20 + [12.0, 6.0, 12.0, 12.0, 6.0]))
    assert fired == []
    fired = feed(rules, _subs([12.0, 12.0, 12.0], start_n=26))
    assert [(s.rule, s.on, s.frame) for s in fired] == [("hfd_rise", True, 28)]
    fired = feed(rules, _subs([6.0, 12.0, 6.0, 6.0], start_n=29))
    assert fired == []  # 1 good, 1 bad, 2 good: not 3 in a row
    fired = feed(rules, _subs([6.1], start_n=33))
    assert [(s.rule, s.on) for s in fired] == [("hfd_rise", False)]
    assert "3 frames" in fired[0].why


def test_baselines_are_per_filter():
    rules = NightRules()
    # IR near 6 px, LP near 10 px, alternating: no filter rises against its own baseline.
    subs = []
    for i in range(60):
        f, hfd = ("IR", 6.0) if i % 2 == 0 else ("LP", 10.0)
        subs.append(Sub(n=i + 1, t=RUN_START + 50 * i, hfd=hfd, stars=3000, filter=f))
    assert feed(rules, subs) == []
    fired = feed(
        rules,
        [
            Sub(n=61 + i, t=RUN_START + 50 * (61 + i), hfd=16.0, stars=3000, filter="LP")
            for i in range(3)
        ],
    )
    assert [s.cause for s in fired] == ["hfd_rise:LP"]
    assert fired[0].title.startswith("LP: HFD 16.0 px = 1.6×")


def test_frames_without_a_value_do_not_count():
    rules = NightRules()
    fired = feed(rules, _subs([6.0] * 20 + [12.0, None, 12.0, None, 12.0]))  # type: ignore[list-item]
    assert [(s.rule, s.frame) for s in fired] == [("hfd_rise", 25)]


def test_the_star_count_drop_fires_like_the_degraded_september_7_run():
    # functional-spaces §4.10: 826 stars against about 3 500 would fire.
    rules = NightRules()
    fired = feed(rules, _subs([3500] * 20 + [826] * 3, key="stars"))
    assert [(s.rule, s.frame) for s in fired] == [("star_drop", 23)]
    assert fired[0].title == "826 stars = 0.24× the first 20 frames"


def test_comparisons_used_fire_and_clear():
    rules = NightRules()
    seq = [5, 2, 4, 2, 2, None, 2, 3, 3, 3]
    fired = []
    for i, c in enumerate(seq, start=1):
        fired += rules.add_measured(c, i, RUN_START + i)
    assert [(s.rule, s.on, s.frame) for s in fired] == [
        ("comps_low", True, 7),  # 2, 2, (no target point), 2
        ("comps_low", False, None),
    ]
    assert fired[0].title == "2 comparisons used for 3 frames"


def test_tracker_lost_counts_s35_and_s48_skips():
    rules = NightRules()
    fired = rules.add_skipped("field_lost", 1, 1.0) + rules.add_skipped("field_lost", 2, 2.0)
    assert fired == []
    fired = rules.add_skipped("no_comparison", 3, 3.0)  # not a tracking failure
    assert fired == []
    fired = rules.add_skipped("lock_lost", 4, 4.0)
    assert [(s.rule, s.on, s.frame) for s in fired] == [("tracker_lost", True, 4)]
    assert "S48" in fired[0].detail
    out = []
    for n in (5, 6, 7):
        out += rules.add_measured(5, n, float(n))
    assert [(s.rule, s.on) for s in out] == [("tracker_lost", False)]


def test_thresholds_come_from_the_config_keys():
    values = {"alerts.hfd_factor": 2.0, "alerts.consecutive_frames": 2, "alerts.baseline_frames": 5}
    th = Thresholds.from_config(lambda key, default: values.get(key, default))
    assert (th.hfd_factor, th.consecutive, th.baseline, th.star_factor) == (2.0, 2, 5, 0.7)
    rules = NightRules(th)
    fired = feed(rules, _subs([6.0] * 5 + [11.0, 13.0, 13.0]))
    assert [(s.rule, s.frame) for s in fired] == [("hfd_rise", 8)]  # 13 > 12, twice


def test_evaluation_is_cheap():
    """Per-frame evaluation runs on the attention thread; it stays far below a frame."""
    started = time.perf_counter()
    for _ in range(5):
        replay(NIGHT)
    per_frame = (time.perf_counter() - started) / (5 * len(NIGHT))
    assert per_frame < 0.002, per_frame


# ---------------------------------------------------------------------------
# The service: driven by the events it watches
# ---------------------------------------------------------------------------


class Clock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return datetime.fromtimestamp(self.t, timezone.utc)


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


RUN_ID = "20260925T200453Z"


def seq_record(state: str, **extra) -> dict:
    record = {
        "type": "sequence",
        "state": state,
        "active": state != "idle",
        "run_id": RUN_ID if state not in ("idle", "waiting") else None,
        "object_name": "RR Lyr",
        "frames_total": 195,
        "started_utc": iso(RUN_START),
        "end_utc": iso(RUN_START + 195 * 51.5),
        "cadence_s": 13.0,
        "step_index": 0,
        "autofocus_passes": [],
        "last_result": None,
        "run_root": None,
    }
    record.update(extra)
    return record


class Night:
    """Publishes a run's events on the hub's bus, as the sequence engine does."""

    def __init__(self, client) -> None:
        self.client = client
        self.hub = client.app.state.hub
        self.att = self.hub.attention
        self.clock = Clock(RUN_START)
        self.att.clock = self.clock
        self.frame_seq = 1000

    def publish(self, kind: str, payload: dict) -> None:
        self.hub.bus.publish(kind, None, payload)

    def settle(self) -> dict:
        assert self.att.flush(3.0)
        return self.client.get("/api/attention", headers=AUTH).json()

    def start(self) -> dict:
        self.publish("sequence", seq_record("running", run_id=None))
        self.publish("sequence", seq_record("running"))
        return self.settle()

    def sub(self, n: int, hfd: float = 6.25, stars: int = 2982, filter_name: str = "IR") -> int:
        t = RUN_START + 51.5 * (n - 1)
        self.clock.t = t + 20
        self.frame_seq += 1
        self.publish(
            "frame_saved",
            {
                "type": "frame_saved",
                "source": "sequence",
                "frame_type": "light",
                "filter": filter_name,
                "date_obs": iso(t),
                "frame_seq": self.frame_seq,
                "path": "/nonexistent/sub.fit",
                "run_root": None,
                "record": {"hfd": hfd, "star_count": stars},
            },
        )
        return self.frame_seq

    def measured(self, seq: int, comps: int) -> None:
        self.publish(
            "photometry_point",
            {"type": "photometry_point", "frame_seq": seq, "role": "target",
             "point": {"comps_used": comps}},
        )  # fmt: skip
        self.publish(
            "photometry",
            {"type": "photometry", "state": "measured", "reason": None,
             "message": f"1 point(s) on frame #{seq}", "last": {"frame_seq": seq}},
        )  # fmt: skip

    def skipped(self, seq: int, reason: str = "field_lost") -> None:
        self.publish(
            "photometry",
            {"type": "photometry", "state": "skipped", "reason": reason,
             "message": f"Skipped frame #{seq}: …", "last": None},
        )  # fmt: skip

    def end(self, reason: str = "completed", message: str = "Sequence complete.") -> dict:
        result = {
            "completed": reason == "completed",
            "reason": reason,
            "message": message,
            "frames_saved": 30,
            "frames_total": 195,
            "run_root": None,
            "started_utc": iso(RUN_START),
            "ended_utc": iso(self.clock.t),
        }
        self.publish("sequence", seq_record("idle", run_id=None, last_result=result))
        return self.settle()


@pytest.fixture
def night(make_client):
    return Night(make_client())


def active_rules(state: dict) -> list[str]:
    return [i["rule"] for i in state["active"]]


def test_a_run_raises_its_items_once_with_hysteresis_and_a_shared_ack(night):
    state = night.start()
    assert active_rules(state) == ["run_started"]
    started = state["active"][0]
    assert started["level"] == "info" and started["kind"] == "event"
    assert started["title"] == "Run started · RR Lyr · 195 frames · ends about 22:52 UTC"
    assert started["sound"] is False  # info is silent by default (alerts.sound_info)
    assert state["counts"]["unacked"] == 0
    for n in range(1, 21):
        night.sub(n)
    for n in range(21, 24):
        night.sub(n, hfd=17.5)
    state = night.settle()
    assert active_rules(state) == ["hfd_rise", "run_started"]  # attention before info
    item = state["active"][0]
    assert item["frame"] == 23 and item["level"] == "attention" and item["kind"] == "condition"
    assert item["title"] == "HFD 17.5 px = 2.8× the first 20 frames"
    assert item["action"] == {"to": "focus", "label": "Focus view"}
    assert item["sound"] is True and item["repeat_s"] is None
    assert state["counts"] == {"critical": 0, "attention": 1, "info": 1, "unacked": 1}
    assert state["last_change"] == {"change": "raised", "id": item["id"]}
    assert "HFD rise: HFD 17.5 px = 2.8× the first 20 frames" in log_messages(night.client)
    # More bad frames: the same item, no storm.
    for n in range(24, 30):
        night.sub(n, hfd=18.0)
    state = night.settle()
    assert [i["id"] for i in state["active"]].count(item["id"]) == 1
    assert len(state["active"]) == 2
    # Any client acknowledges; every client sees it.
    answer = night.client.post(
        f"/api/attention/{item['id']}/ack", json={"by": "tablet"}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text
    acked = answer.json()["active"][0]
    assert acked["acked"] and acked["acked_by"] == "tablet" and acked["active"]
    assert answer.json()["counts"]["unacked"] == 0
    assert answer.json()["last_change"] == {"change": "acked", "id": item["id"]}
    assert night.client.post(f"/api/attention/{item['id']}/ack", headers=AUTH).status_code == 200
    # Three good frames clear it (resolved, into the history).
    for n in range(30, 33):
        night.sub(n)
    state = night.settle()
    assert active_rules(state) == ["run_started"]
    cleared = state["history"][0]
    assert cleared["id"] == item["id"] and cleared["cleared_reason"] == "resolved"
    assert any(
        m.startswith("Cleared: HFD rise — HFD back under") for m in log_messages(night.client)
    )
    # It fires again within 10 min: the same item reopens and needs a new acknowledgement
    # (technical review). Within 15 min of its tone, a non-critical one stays quiet:
    # no new tone (``tone`` unchanged) and no new log line.
    night.clock.t += 60
    for n in range(33, 36):
        night.sub(n, hfd=17.0)
    state = night.settle()
    again = state["active"][0]
    assert again["id"] == item["id"] and again["occurrences"] == 2
    assert not again["acked"] and again["acked_by"] is None and again["tone"] == 1
    assert state["counts"]["unacked"] == 1
    assert state["last_change"]["change"] == "reopened"
    assert not any("HFD rise again" in m for m in log_messages(night.client))
    # The end: open conditions clear (run_ended), the outcome is an info event.
    state = night.end()
    assert active_rules(state) == ["run_ended", "run_started"]
    assert state["active"][0]["title"] == "Run complete · 30 frames"
    assert state["history"][0]["cleared_reason"] == "run_ended"


def test_a_client_joining_mid_run_receives_the_list_and_its_history(night):
    night.start()
    for n in range(1, 24):
        night.sub(n, hfd=6.25 if n <= 20 else 20.0)
    night.settle()
    with night.client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        event = receive_until(ws, lambda m: m.get("type") == "attention")
    assert active_rules(event) == ["hfd_rise", "run_started"]
    assert event["counts"]["unacked"] == 1
    assert event["sound"] == {"level": "normal", "info": False, "repeat_s": 30}
    assert event["thresholds"]["alerts.hfd_factor"] == 1.5


def test_the_attention_event_follows_every_change(night):
    with night.client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        receive_until(ws, lambda m: m.get("type") == "attention")  # the joining snapshot
        night.start()
        event = receive_until(ws, lambda m: m.get("type") == "attention" and m["active"])
        assert event["last_change"]["change"] == "raised"
        item_id = event["active"][0]["id"]
        night.client.post(f"/api/attention/{item_id}/ack", headers=AUTH)
        event = receive_until(
            ws,
            lambda m: m.get("type") == "attention"
            and (m.get("last_change") or {}).get("change") == "acked",
        )
        # An acknowledged event leaves the active list.
        assert event["active"] == [] and event["history"][0]["cleared_reason"] == "acknowledged"


def test_comparisons_and_tracker_rules_from_the_photometry_outcomes(night):
    night.start()
    for n in range(1, 4):
        seq = night.sub(n)
        night.measured(seq, comps=2)
    state = night.settle()
    assert active_rules(state)[0] == "comps_low"
    assert state["active"][0]["frame"] == 3 and state["active"][0]["action"]["to"] == "field"
    for n in range(4, 7):
        night.skipped(night.sub(n), reason="lock_lost")
    state = night.settle()
    assert active_rules(state)[:2] == ["tracker_lost", "comps_low"]
    tracker = state["active"][0]
    assert "S48" in tracker["detail"]
    assert tracker["values"]["reasons"] == "lock_lost, lock_lost, lock_lost"
    # The same outcome re-sent counts once.
    night.publish(
        "photometry",
        {"state": "skipped", "reason": "lock_lost", "message": "Skipped frame #1006: …"},
    )
    for n in range(7, 10):
        night.measured(night.sub(n), comps=5)
    state = night.settle()
    assert active_rules(state) == ["run_started"]
    summary = night.att.run_summary(RUN_ID)
    assert summary["frames_measured"] == 6
    assert summary["frames_skipped"] == {"field_lost": 0, "lock_lost": 3, "other": 0}
    assert summary["attention"] == 2 and summary["info"] == 1


def test_no_new_frame_is_critical_repeats_and_clears(night):
    night.start()
    for n in range(1, 11):
        night.sub(n)
    night.settle()
    last = RUN_START + 51.5 * 9  # limit: max(2 × 51.5, 51.5 + 60) = 111.5 s
    night.clock.t = last + 111.5 + 2
    state = wait_for(
        lambda: (s := night.settle())["counts"]["critical"] and s, timeout=4.0
    )  # the 1 s timer
    item = state["active"][0]
    assert item["rule"] == "no_frame" and item["level"] == "critical"
    assert item["repeat_s"] == 30 and item["sound"] is True
    assert item["values"]["limit_s"] == pytest.approx(111.5)
    assert item["title"].startswith("No new frame since ")
    night.sub(11)
    state = night.settle()
    assert "no_frame" not in active_rules(state)
    # Paused: no silence alarm however long.
    night.publish("sequence", seq_record("paused"))
    night.clock.t += 3600
    time.sleep(1.3)
    assert "no_frame" not in active_rules(night.settle())


def test_a_run_stopped_on_error_is_critical_until_acknowledged(night):
    night.start()
    state = night.end("camera_error", "Camera: exposure timed out")
    item = state["active"][0]
    assert item["rule"] == "run_error" and item["level"] == "critical"
    assert item["title"] == "Run stopped: Camera: exposure timed out"
    assert item["repeat_s"] == 30 and item["kind"] == "event"
    state = night.client.post("/api/attention/ack-all", json={"by": "laptop"}, headers=AUTH).json()
    assert state["active"] == []
    assert {i["rule"] for i in state["history"][:2]} == {"run_error", "run_started"}
    assert all(i["acked_by"] == "laptop" for i in state["history"][:2])


def test_a_new_run_retires_the_previous_runs_events(night):
    night.start()
    night.end("stopped", "Stopped by the observer.")
    state = night.settle()
    assert active_rules(state) == ["run_ended", "run_started"]
    assert state["active"][0]["title"] == "Run stopped by the observer · 30 of 195 frames"
    state = night.start()
    assert active_rules(state) == ["run_started"]
    assert {i["cleared_reason"] for i in state["history"][:2]} == {"new_run"}


def test_ack_errors(night):
    answer = night.client.post("/api/attention/nope/ack", headers=AUTH)
    assert answer.status_code == 404 and answer.json()["error"]["code"] == "not_found"
    answer = night.client.post("/api/attention/x/ack", json={"by": "x" * 65}, headers=AUTH)
    assert answer.status_code == 400


def test_the_thresholds_are_config_keys_in_the_alerts_category(night):
    meta = night.client.get("/api/config", headers=AUTH).json()["meta"]
    alerts = {k: m for k, m in meta.items() if m["category"] == "alerts"}
    assert set(alerts) == {
        "alerts.sound", "alerts.sound_info", "alerts.repeat_critical_s", "alerts.keep_awake",
        "alerts.consecutive_frames", "alerts.baseline_frames", "alerts.hfd_factor",
        "alerts.star_factor", "alerts.comparisons_min", "alerts.no_frame_factor",
        "alerts.no_frame_margin_s", "alerts.altitude_warn_min", "alerts.disk_minutes",
    }  # fmt: skip
    assert [o["value"] for o in alerts["alerts.sound"]["options"]] == ["off", "soft", "normal"]
    answer = night.client.patch(
        "/api/config", json={"alerts.consecutive_frames": 2, "alerts.sound": "soft"}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text
    night.start()
    for n in range(1, 23):
        night.sub(n, hfd=6.25 if n <= 20 else 30.0)
    state = night.settle()
    assert state["active"][0]["rule"] == "hfd_rise" and state["active"][0]["frame"] == 22
    assert state["sound"]["level"] == "soft"
    assert (
        night.client.patch("/api/config", json={"alerts.sound": "loud"}, headers=AUTH).status_code
        == 400
    )


def test_a_device_lost_during_a_run_is_critical_and_clears_on_reconnect(make_client, tmp_path):
    from tests.server.conftest import science_client

    client = science_client(make_client, tmp_path, connect=("mount", "camera"))
    night = Night(client)
    night.start()
    assert client.delete("/api/devices/mount", headers=AUTH).status_code == 200
    state = night.settle()
    item = state["active"][0]
    assert item["rule"] == "device_lost" and item["cause"] == "device_lost:mount"
    assert item["level"] == "critical" and "saved without pointing" in item["detail"]
    answer = client.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
    assert answer.status_code == 200
    state = night.settle()
    assert active_rules(state) == ["run_started"]
    assert state["history"][0]["cleared_reason"] == "resolved"


def test_the_snapshot_stays_cheap_with_a_full_history(night):
    night.start()
    with night.att._lock:
        for i in range(200):
            night.att._history.append(
                {**night.att._active[next(iter(night.att._active))], "id": f"h{i}"}
            )
    started = time.perf_counter()
    for _ in range(50):
        night.att.snapshots(1)
    per = (time.perf_counter() - started) / 50
    assert per < 0.02, per  # on the event loop at connect: milliseconds


def test_unknown_values_are_ignored():
    rules = NightRules()
    assert rules.silence(10.0, True, None) == []
    assert rules.add_skipped("other", None, None) == []
    assert math.isinf(rules.silence_limit())
    assert rules.silence_limit(planned=13.0) == pytest.approx(86.0)  # 2 × 13 + 60 before 2 saves


def test_the_altitude_rule_warns_ahead_then_below_then_clears(night, monkeypatch):
    from argos.core.imaging import sky_geometry
    from argos.core.photometry.airmass import julian_date

    answer = night.client.patch(
        "/api/config", json={"site.latitude": 45.0, "site.longitude": 5.0}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text
    monkeypatch.setattr(night.hub.sequence, "target_radec", lambda: (19.44, 42.78))
    jd0 = julian_date(datetime.fromtimestamp(RUN_START, timezone.utc))
    slope = {"deg_per_min": -1.0}

    def fake_horizontal(jd, ra_h, dec, lat, lon):  # 40.5° at the start, 1°/min down
        return 40.5 + slope["deg_per_min"] * (jd - jd0) * 1440.0, 180.0

    monkeypatch.setattr(sky_geometry, "horizontal_at", fake_horizontal)
    night.start()  # 40.5°: below 30° in 10.5 min (< 15 min)
    state = wait_for(lambda: "altitude" in active_rules(s := night.settle()) and s, timeout=4)
    item = next(i for i in state["active"] if i["rule"] == "altitude")
    assert item["title"] == "Target drops below 30° at 20:15 UTC"  # 1 min steps
    assert item["values"]["limit_deg"] == 30.0 and item["action"]["to"] == "run"
    night.clock.t = RUN_START + 11 * 60  # 29.5°: below now

    def below_now():
        state = night.settle()
        return any(i["title"].startswith("Target below") for i in state["active"]) and state

    state = wait_for(below_now, timeout=4)
    below = next(i for i in state["active"] if i["rule"] == "altitude")
    assert below["id"] == item["id"] and below["title"] == "Target below the 30° limit (29.5°)"
    slope["deg_per_min"] = 0.0  # 40.5° and steady: above the limit + 0.5°, nothing ahead
    night.clock.t += 60
    state = wait_for(lambda: "altitude" not in active_rules(s := night.settle()) and s, timeout=4)
    assert state["history"][0]["id"] == item["id"]


def test_the_disk_rule_uses_the_newest_file_and_the_cadence(night, monkeypatch, tmp_path):
    from argos.server import attention as module

    sub = tmp_path / "sub.fit"
    sub.write_bytes(b"\0" * 16_000)  # 16 kB per frame
    free = {"bytes": 10**9}

    class Usage:
        def __init__(self, path):
            self.free = free["bytes"]

    monkeypatch.setattr(module.shutil, "disk_usage", Usage)
    night.start()

    def saved(n: int) -> None:
        t = RUN_START + 51.5 * (n - 1)
        night.clock.t = t + 5
        night.publish(
            "frame_saved",
            {"source": "sequence", "frame_type": "light", "filter": "IR", "date_obs": iso(t),
             "frame_seq": 5000 + n, "path": str(sub), "run_root": str(tmp_path),
             "record": {"hfd": 6.0, "star_count": 3000}},
        )  # fmt: skip

    for n in (1, 2, 3):
        saved(n)
    assert "disk" not in active_rules(night.settle())
    # 30 min at 51.5 s = 34.95 frames of 16 kB = 559 kB: 500 kB free fires.
    free["bytes"] = 500_000
    saved(4)
    state = night.settle()
    item = next(i for i in state["active"] if i["rule"] == "disk")
    assert item["title"] == "Disk space for under 30 min of frames (500.0 kB free)"
    assert item["values"]["minutes_left"] == pytest.approx(500_000 / 16_000 * 51.5 / 60)
    free["bytes"] = 600_000  # above the need but within 10 %: still open
    saved(5)
    assert "disk" in active_rules(night.settle())
    free["bytes"] = 700_000
    saved(6)
    assert "disk" not in active_rules(night.settle())


# -- the reviews' fixes (wave 6b fixer) ------------------------------------------------


def _saved(night, n: int, start: float, saved: float, *, frame_type: str = "light") -> None:
    night.clock.t = saved
    night.frame_seq += 1
    night.publish(
        "frame_saved",
        {"type": "frame_saved", "source": "sequence", "frame_type": frame_type,
         "filter": "IR", "date_obs": iso(start), "t": iso(saved), "frame_seq": night.frame_seq,
         "path": "/nonexistent/sub.fit", "run_root": None,
         "record": {"hfd": 10.8, "star_count": 3181}},
    )  # fmt: skip


def test_the_silence_runs_from_the_save_not_the_start(night):
    """Science review: the silence was counted from the newest sub's start, but a
    client learns of a frame when it is saved. RR Lyr 2026-09-25: sub 1 started at
    20:04:56.6 and was saved 44.5 s later; sub 2 was saved at 20:06:48.9. The
    critical alarm fired at 20:06:41 (limit 104.5 s from the start), as at the start
    of all 9 of the owner's runs. Counted from the save, with 2 × floor + 60 s
    before two saves, the limit is 149 s; a real freeze still fires."""
    start1 = datetime(2026, 9, 25, 20, 4, 56, 600000, tzinfo=timezone.utc).timestamp()
    saved1 = start1 + 44.5
    saved2 = datetime(2026, 9, 25, 20, 6, 48, 900000, tzinfo=timezone.utc).timestamp()
    night.start()
    _saved(night, 1, start1, saved1)
    night.settle()
    night.clock.t = saved2 - 0.1  # 112.2 s after sub 1 started
    time.sleep(1.3)  # one tick of the timer
    assert "no_frame" not in active_rules(night.settle())  # fired at 20:06:41 before
    _saved(night, 2, saved2 - 44.5, saved2)
    night.settle()
    night.clock.t = saved2 + 136.0  # limit max(2 × 67.8, 67.8 + 60) = 135.6 s
    state = wait_for(lambda: (s := night.settle())["counts"]["critical"] and s, timeout=4.0)
    item = next(i for i in state["active"] if i["rule"] == "no_frame")
    assert item["title"] == "No new frame since 20:06:48 UTC (limit 136 s)"
    assert "Last frame #2 saved at 20:06:48 UTC" in item["detail"]


def test_a_reopened_item_needs_a_new_acknowledgement(night):
    """Technical review: a condition that came back within 10 min of its clear kept
    its acknowledgement, so a second "No new frame" was silent: no tone, no chip,
    no Watch row. A reopened item is unacknowledged and a critical one sounds."""
    night.start()
    for n in range(1, 11):
        night.sub(n)
    last = RUN_START + 51.5 * 9
    night.clock.t = last + 113.5
    state = wait_for(lambda: (s := night.settle())["counts"]["critical"] and s, timeout=4.0)
    item = next(i for i in state["active"] if i["rule"] == "no_frame")
    assert item["tone"] == 1
    answer = night.client.post(f"/api/attention/{item['id']}/ack", json={"by": "A"}, headers=AUTH)
    assert answer.json()["counts"]["unacked"] == 0
    night.sub(11)  # frames again: resolved
    assert "no_frame" not in active_rules(night.settle())
    night.clock.t = RUN_START + 51.5 * 10 + 300.0  # frozen again, 5 min later
    state = wait_for(lambda: (s := night.settle())["counts"]["critical"] and s, timeout=4.0)
    again = next(i for i in state["active"] if i["rule"] == "no_frame")
    assert again["id"] == item["id"] and again["occurrences"] == 2
    assert not again["acked"] and again["acked_by"] is None  # acked by "A" before the fix
    assert again["tone"] == 2  # a critical item always sounds again
    assert state["counts"]["unacked"] == 1
    assert any(m.startswith("No new frame again: ") for m in log_messages(night.client))


def test_the_run_stopped_log_line_says_it_once(night):
    night.start()
    night.end("camera_error", "Camera: exposure timed out")
    messages = log_messages(night.client)
    assert "Run stopped: Camera: exposure timed out" in messages
    assert not any("Run stopped: Run stopped" in m for m in messages)


def test_a_run_without_light_frames_has_no_altitude_rule(make_client):
    """Technical review: a Dark-only run (the wrap-up's darks at dawn, under the last
    run's object) raised "Target below the 30° limit" with two tones, while the
    preflight said "Calibration frames only: no altitude needed"."""
    from types import SimpleNamespace

    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    hub = make_client().app.state.hub
    hub.observation._record = {
        **hub.observation._record,
        "target": {"ra_hours": 12.0, "dec_deg": -60.0},
    }
    darks = SequencePlan(steps=[SequenceStep(frame_type="Dark", count=4, exposure_s=1.0)])
    hub.sequence._run = SimpleNamespace(plan=darks)
    try:
        assert hub.sequence.target_radec() is None  # (12.0, -60.0) before the fix
        lights = SequencePlan(steps=[SequenceStep(frame_type="Light", count=4)])
        hub.sequence._run = SimpleNamespace(plan=lights)
        assert hub.sequence.target_radec() == (12.0, -60.0)
    finally:
        hub.sequence._run = None


def test_the_altitude_rule_takes_the_mounts_altitude_when_the_site_disagrees(night, monkeypatch):
    """Science review: on RR Lyr 2026-09-25 (a wrong Settings site, X3) the rule said
    13.9° from the site while the mount read 75°: a false alert all run. When the
    site check disagrees, the mount's own altitude decides, with nothing extrapolated;
    without a mount reading there is no verdict."""
    from argos.server.capture import Pointing

    answer = night.client.patch(
        "/api/config", json={"site.latitude": 45.0, "site.longitude": 5.0}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text
    hub = night.hub
    monkeypatch.setattr(hub.sequence, "target_radec", lambda: (19.44, 42.78))
    monkeypatch.setattr(hub.site_check, "record", lambda: {"state": "mismatch"})
    reading = {"pointing": Pointing(19.44, 42.78, 75.4, 300.0)}
    monkeypatch.setattr(hub, "_pointing", lambda: reading["pointing"])
    from argos.core.imaging import sky_geometry

    monkeypatch.setattr(sky_geometry, "horizontal_at", lambda *a: (13.9, 300.0))
    night.start()
    time.sleep(1.3)
    assert "altitude" not in active_rules(night.settle())  # 13.9° from the site before
    reading["pointing"] = Pointing(19.44, 42.78, 25.0, 300.0)
    night.att._run.next_slow = 0.0
    state = wait_for(lambda: "altitude" in active_rules(s := night.settle()) and s, timeout=4)
    item = next(i for i in state["active"] if i["rule"] == "altitude")
    assert item["title"] == "Target below the 30° limit (25.0°)"
    assert "from the mount: the Settings site disagrees with it" in item["detail"]


def test_the_disk_rule_needs_only_the_runs_remaining_frames(night, monkeypatch, tmp_path):
    """Science review: an 80-sub run of 1.3 GB raised "under 30 min of frames" with
    18.9 GB free (30 min at its 1.26 s cadence is 1 428 frames)."""
    from argos.server import attention as module

    sub = tmp_path / "sub.fit"
    sub.write_bytes(b"\0" * 16_000)

    class Usage:
        def __init__(self, path):
            self.free = 100_000  # 6 frames of 16 kB; 30 min at 51.5 s is 35 frames

    monkeypatch.setattr(module.shutil, "disk_usage", Usage)
    night.publish("sequence", seq_record("running", run_id=None, frames_total=8))
    night.publish("sequence", seq_record("running", frames_total=8))
    for n in range(1, 4):
        t = RUN_START + 51.5 * (n - 1)
        night.clock.t = t + 5
        night.publish(
            "frame_saved",
            {"source": "sequence", "frame_type": "light", "filter": "IR", "date_obs": iso(t),
             "frame_seq": 6000 + n, "path": str(sub), "run_root": str(tmp_path),
             "record": {"hfd": 6.0, "star_count": 3000}},
        )  # fmt: skip
    state = night.settle()
    assert "disk" not in active_rules(state)  # 5 frames left: 80 kB, fired before the fix
    Usage.__init__ = lambda self, path: setattr(self, "free", 50_000)
    night.publish(
        "frame_saved",
        {"source": "sequence", "frame_type": "light", "filter": "IR",
         "date_obs": iso(RUN_START + 160), "frame_seq": 6010, "path": str(sub),
         "run_root": str(tmp_path), "record": {"hfd": 6.0, "star_count": 3000}},
    )  # fmt: skip
    item = next(i for i in night.settle()["active"] if i["rule"] == "disk")
    assert item["title"] == "Disk space short of the run's 4 remaining frames (50.0 kB free)"


def test_alert_numbers_follow_the_ui_conventions():
    """Design review: the server's texts bypassed format/number: "2010 stars",
    "frames 23-25", a hyphen-minus for negatives (web/src/lib/format/number.ts)."""
    from argos.server.attention import _fixed, _int, _span

    assert _int(2010) == "2\u202f010" and _int(826) == "826" and _int(-1250) == "\u22121\u202f250"
    assert _int(1234567) == "1\u202f234\u202f567"
    assert _fixed(-18.94, 1) == "\u221218.9" and _fixed(-0.04, 1) == "0.0"
    assert _span(23, 25) == "23 … 25"
    rules = NightRules()
    fired = feed(rules, _subs([3500] * 20 + [2010] * 3, key="stars"))
    assert fired[0].title == "2\u202f010 stars = 0.57× the first 20 frames"
    assert "fewer than 0.7 × 3\u202f500 stars" in fired[0].detail
    fired = feed(NightRules(), _subs([6.0] * 20 + [17.5, 17.6, 23.6]))
    assert "frames 21 … 23" in fired[0].detail
