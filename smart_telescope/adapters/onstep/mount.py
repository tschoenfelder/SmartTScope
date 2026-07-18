"""SmartTScope shim over ``onstep_adapter.mount`` (see SYNC.md).

All LX200/serial protocol logic lives in the pip-installed ``onstep_adapter``
package. This file may contain ONLY:

- permanent SmartTScope-specific wrappers (interface adapters, config glue),
- documented SYNC-OVERRIDEs for gaps not yet shipped upstream (each tagged
  with the REQ-ID tracked in SYNC.md), and
- the FSM mapping between upstream's 6-state ``MountState`` and SmartTScope's
  7-state enum (AT_HOME derived from the decoded ``:GU#`` ``at_home`` flag).

Never patch protocol behavior here without recording it in SYNC.md first —
gaps go upstream as change requests (issue on tschoenfelder/OnStepAdapter,
filed only with explicit user approval).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import replace
from datetime import datetime, timezone

# Re-exported upstream module-level helpers so existing SmartTScope imports of
# ``smart_telescope.adapters.onstep.mount._x`` keep working. NOTE: patching
# these names here does NOT affect upstream-internal calls — patch
# ``onstep_adapter.mount.<name>`` in tests instead.
from onstep_adapter.mount import (  # noqa: F401
    _compute_altaz_stdlib,
    _compute_altaz_stdlib_at,
    _counterweight_safety_state,
    _decode_onstep_status,
    _default_safety_config,
    _distance_m,
    _evaluate_onstep_meridian_path_coverage,
    _evaluate_onstep_operational_protection,
    _format_dec,
    _format_limit_degrees,
    _format_onstep_utc_offset,
    _format_ra,
    _format_site_degrees,
    _instrument_to_mount_axes,
    _julian_date,
    _lst_hours,
    _optional_float,
    _optional_str,
    _parse_dec,
    _parse_degrees,
    _parse_onstep_local_datetime,
    _parse_ra,
    _stored_park_to_dict,
)
from onstep_adapter.mount import OnStepMount as _BaseOnStepMount

from ...ports.mount import MountPort, MountPosition, MountState  # noqa: F401

_log = logging.getLogger(__name__)


# ── REQ-ST-008 helpers (pending upstream adoption — stay local either way) ────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 lat/lon coordinates."""
    R = 6_371_000.0
    lat1r, lat2r, lon1r, lon2r = map(math.radians, (lat1, lat2, lon1, lon2))
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _lx200_round_degrees(value: float) -> float:
    """Round to arcminute precision — matches what LX200 ±DD*MM site format can store."""
    sign = 1.0 if value >= 0 else -1.0
    v = abs(value)
    deg = int(v)
    minutes = int(round((v - deg) * 60.0))
    if minutes >= 60:
        deg += 1
        minutes -= 60
    return sign * (deg + minutes / 60.0)


class OnStepMount(_BaseOnStepMount, MountPort):
    """SmartTScope-facing OnStep mount: upstream implementation + shim layer."""

    # ── ONS31-101: FSM mapping (upstream 6 states + at_home flag → 7 states) ──

    def get_state(self) -> MountState:
        """Map the upstream state + decoded ``:GU#`` flags onto SmartTScope's FSM.

        HOME is a mechanical flag upstream (``last_decoded_status["at_home"]``),
        deliberately not an enum state. at_home is checked before slewing:
        during ``:hC#`` travel OnStep keeps the goto-active flag set until 'H'
        appears (see M9-021). The first 'H' observation also confirms HOME
        authority so ``set_park_position_from_current()`` works.
        ``_at_mechanical_home`` keeps AT_HOME sticky between polls (the raw 'H'
        flag can clear quickly); its lifecycle is managed upstream and by the
        ``enable_tracking()`` override below.
        """
        upstream_state = super().get_state()  # refreshes :GU#
        if upstream_state.name == "UNKNOWN":
            return MountState.UNKNOWN
        decoded = self.last_decoded_status or {}
        if decoded.get("parked"):
            return MountState.PARKED
        if decoded.get("at_home"):
            if not self._at_mechanical_home:
                self._at_mechanical_home = True
                self.confirm_home_position()
            return MountState.AT_HOME
        # M9-036: observed motion beats the sticky authority flag. The flag
        # re-arms on the genuine H still visible in the first seconds of a
        # park slew leaving home; letting it override SLEWING displayed
        # AT HOME through the entire park travel (hardware 2026-07-17).
        # Ordering note: the decoded at_home check above still wins over
        # SLEWING on purpose (M9-021 — H appears while the goto-active flag
        # may still be set at the end of a home slew).
        if upstream_state.name == "SLEWING":
            return MountState.SLEWING
        if self._at_mechanical_home:
            return MountState.AT_HOME
        return MountState[upstream_state.name]

    # ── M9-036: stop() invalidates mechanical-home authority ──────────────────

    def stop(self) -> None:
        # A manual/emergency :Q# means the mount may have halted anywhere —
        # the sticky home authority is no longer trustworthy. Upstream
        # stop() does not clear ``_at_mechanical_home`` (upstream ask
        # recorded in SYNC.md); route the invalidation through upstream's
        # public ``note_external_motion()``. If the mount really is still
        # at home, the next poll re-detects the genuine H flag and re-arms.
        super().stop()
        try:
            self.note_external_motion("manual_stop")
        except Exception:  # never let bookkeeping break an emergency stop
            _log.warning("OnStepMount.stop(): note_external_motion failed", exc_info=True)

    # ── ONS31-102: routed unpark (supersedes SAFETY-001/002) ──────────────────

    def unpark(self) -> bool:
        """Unpark via the SDK's routed ``unpark_to_home_stop_tracking()``.

        Actively stops firmware-auto-started tracking and drives the mount to
        HOME instead of locally reinterpreting the reported state. Returns
        whether the unpark itself (``:hR#``) was accepted; an incomplete
        home/stop phase is logged, not retried (M9-027: never blind-resend).
        """
        result = self.unpark_to_home_stop_tracking()
        unparked = bool((result.get("unpark") or {}).get("ok"))
        if not bool(result.get("ok")):
            _log.warning(
                "OnStepMount.unpark(): unpark_to_home_stop_tracking incomplete "
                "(unpark_ok=%s at_home=%s final_state=%s)",
                unparked,
                result.get("at_home"),
                result.get("final_state"),
            )
        return unparked

    # ── SYNC-OVERRIDE REQ-ST-004 (not in upstream v0.3.1 wheel) ───────────────

    def enable_tracking(self) -> bool:
        # SYNC-OVERRIDE REQ-ST-004: at-home bypass. At the mechanical home
        # position the RA/Dec readback is unreliable (stale park RA → LST − RA
        # can yield an HA far outside limits). Safety lock and astronomy
        # readiness still apply; positional checks (HA/alt/dec limits) do not —
        # the home pose is mechanically safe. Verbatim copy of the local
        # pre-migration method (minus the retired _explicit_tracking_started
        # flag); delete once upstream ships REQ-ST-004.
        at_home = self._at_mechanical_home or bool(
            (self._last_decoded_status or {}).get("at_home")
        )
        if at_home:
            self._raise_if_locked("enable_tracking")
            self._raise_if_not_astronomy_ready("enable_tracking")
        else:
            pos = self.get_position()
            self._check_target_safe("enable_tracking", pos.ra, pos.dec, margin_deg=0.25)
        try:
            r = self._bus.send_fixed(":Te#", size=1, timeout=2.0)
        except TimeoutError as exc:
            raise RuntimeError("OnStep serial bus busy during enable_tracking") from exc
        ok = r == "1"
        if ok:
            self._at_mechanical_home = False
            if not self._meridian_flip_completed:
                self.begin_meridian_tracking_session()
            self._persist_last_state(last_command="enable_tracking", force=True)
        else:
            _log.warning("OnStepMount.enable_tracking(): OnStep rejected :Te# with reply %r", r)
        return ok

    # ── SYNC-OVERRIDE REQ-ST-007 (not in upstream v0.3.1 wheel) ───────────────

    def motion_safety_preflight(
        self,
        *,
        command: str,
        normal_motion: bool = True,
        margin_deg: float = 0.0,
    ) -> dict[str, object]:
        """Read one fresh logical/mechanical safety snapshot before motion.

        SYNC-OVERRIDE REQ-ST-007: verbatim copy of the local pre-migration
        method. Differs from upstream v0.3.1 in exactly two pier-side guards:
        (a) stale ``:Gm#`` suppression when home is confirmed and axis2 < 15°,
        (b) ``pier_side_axis_inconsistent`` blocker suppressed in terminal
        state (parked/at-home). Delete once upstream ships REQ-ST-007 —
        re-diff on every upstream release.
        """
        sample_started = time.monotonic()
        sampled_at = datetime.now(timezone.utc)
        blockers: list[str] = []

        try:
            state = self.get_state()
        except Exception as exc:
            state = MountState.UNKNOWN
            blockers.append(f"onstep_status_unavailable:{exc}")
        decoded = dict(self._last_decoded_status or {})
        authority = self._mechanical_position_authority()
        at_home = bool(decoded.get("at_home") or self._at_mechanical_home)
        parked = state == MountState.PARKED or bool(decoded.get("parked"))
        terminal_state = parked or at_home

        try:
            direct_pier = self.read_pier_side()
        except Exception as exc:
            direct_pier = {"available": False, "value": None, "raw": "", "command": ":Gm#", "error": str(exc)}
        try:
            logical_axes = self.read_onstep_axis_position()
        except Exception as exc:
            logical_axes = {"available": False, "axis1_deg": None, "axis2_deg": None, "error": str(exc)}

        derived_axes: dict[str, object] | None = None
        if (
            self._home_confirmed
            and isinstance(logical_axes.get("axis1_deg"), (int, float))
            and isinstance(logical_axes.get("axis2_deg"), (int, float))
        ):
            derived_axes = _instrument_to_mount_axes(
                float(logical_axes["axis1_deg"]),
                float(logical_axes["axis2_deg"]),
                self._safety_config.observer_lat,
            )

        direct_pier_value = direct_pier.get("value")
        derived_pier_value = derived_axes.get("pier_side") if isinstance(derived_axes, dict) else None
        if direct_pier_value in {"east", "west"}:
            pier_side = str(direct_pier_value)
            pier_source = "onstep_gm"
        elif derived_pier_value in {"east", "west"}:
            pier_side = str(derived_pier_value)
            pier_source = "home_validated_logical_axes"
        else:
            pier_side = None
            pier_source = "unavailable"
        pier_consistent = not (
            direct_pier_value in {"east", "west"}
            and derived_pier_value in {"east", "west"}
            and direct_pier_value != derived_pier_value
        )
        # :Gm# retains the last GoTo session's pier side across unpark/reboot.
        # When home is confirmed and axis2 is near 0° (CWD home hemisphere), the
        # axis-derived value is authoritative; treat a :Gm# mismatch as stale.
        if not pier_consistent and self._home_confirmed:
            axis2_raw = logical_axes.get("axis2_deg")
            if isinstance(axis2_raw, (int, float)) and abs(float(axis2_raw)) < 15.0:
                pier_consistent = True
        if (
            (decoded.get("tracking") or state == MountState.TRACKING)
            and self._meridian_initial_pier_side is None
            and pier_side in {"east", "west"}
        ):
            self._meridian_initial_pier_side = pier_side

        position: dict[str, float] | None = None
        context: dict[str, object] | None = None
        ha_hours: float | None = None
        sidereal: dict[str, object] = {
            "available": False,
            "raw": "",
            "lst_hours": None,
            "source": "onstep_GS",
        }
        try:
            pos = self.get_position()
            position = {"ra": pos.ra, "dec": pos.dec}
            context = self._target_safety_context(pos.ra, pos.dec, margin_deg)
        except Exception as exc:
            blockers.append(f"logical_position_unavailable:{exc}")
        if position is not None:
            try:
                sidereal_reply = self._send(":GS#")
                onstep_lst_h = _parse_ra(sidereal_reply)
                ha_hours = ((onstep_lst_h - float(position["ra"]) + 12.0) % 24.0) - 12.0
                sidereal = {
                    "available": True,
                    "raw": sidereal_reply,
                    "lst_hours": round(onstep_lst_h, 6),
                    "source": "onstep_GS",
                    "raspberry_context_ha_hours": (
                        context.get("ha_hours") if isinstance(context, dict) else None
                    ),
                }
            except Exception as exc:
                blockers.append(f"onstep_sidereal_time_unavailable:{exc}")

        counterweight = _counterweight_safety_state(
            ha_hours=ha_hours,
            pier_side=pier_side,
            east_limit_h=self._safety_config.ha_east_limit_h,
            west_limit_h=self._safety_config.ha_west_limit_h,
            warning_margin_deg=self._safety_config.meridian_margin_deg,
            preflip_pier_side=self._meridian_initial_pier_side,
            terminal_state=terminal_state,
        )

        if authority.get("state") != "trusted":
            blockers.append("mechanical_position_authority_untrusted")
        if state == MountState.UNKNOWN:
            blockers.append("onstep_state_unknown")
        if decoded.get("park_failed"):
            blockers.append("onstep_park_failed")
        if decoded.get("at_limit"):
            blockers.append("onstep_at_limit")
        if not pier_consistent and not terminal_state:
            blockers.append("pier_side_axis_inconsistent")
        if pier_side is None and not terminal_state:
            blockers.append("pier_side_unavailable")
        if ha_hours is None and not terminal_state:
            blockers.append("hour_angle_unavailable")
        if counterweight.get("hard_limit_reached"):
            blockers.append("counterweight_hard_limit")
        if normal_motion and parked:
            blockers.append("mount_parked")
        if normal_motion and state == MountState.SLEWING:
            blockers.append("mount_already_slewing")

        blockers = list(dict.fromkeys(blockers))
        mechanical_blockers = {
            "mechanical_position_authority_untrusted",
            "onstep_state_unknown",
            "onstep_park_failed",
            "onstep_at_limit",
            "pier_side_axis_inconsistent",
            "pier_side_unavailable",
            "hour_angle_unavailable",
            "counterweight_hard_limit",
        }
        mechanical_safe = not any(
            blocker in mechanical_blockers
            or blocker.startswith("onstep_status_unavailable:")
            or blocker.startswith("logical_position_unavailable:")
            for blocker in blockers
        )
        sample_age_ms = round((time.monotonic() - sample_started) * 1000.0, 3)
        motion_refused = bool(blockers)
        # SYNC-OVERRIDE REQ-ST-009: during a manual jog (see move()), report
        # at_home=False for exactly the two jog preflight commands so
        # upstream _axis_motion()'s hardcoded at-home refusal doesn't fire.
        # Deliberately a post-process on the RETURNED value only: the local
        # at_home/terminal_state above must stay truthful so the pier/HA
        # blockers remain suppressed at home (flipping it earlier would
        # re-add them and refuse the jog with a different reason). All
        # mechanical blockers (motion_refused) are untouched. NOTE: safe
        # today only because runtime.py constructs OnStepClient without
        # motion_calibration — with calibration wired, upstream's projected-
        # target validate_target gate re-activates and needs the upstream
        # manual-jog mode instead (REQ-ST-009 issue).
        report_at_home = at_home
        if (
            getattr(self, "_jog_bypass_active", False)
            and command in ("move_ra_center", "move_dec_center")
        ):
            report_at_home = False
        return {
            "command": command,
            "sampled_at_utc": sampled_at.isoformat(),
            "safety_sample_age_ms": sample_age_ms,
            "state": state.name.lower(),
            "tracking": bool(decoded.get("tracking") or state == MountState.TRACKING),
            "slewing": bool(decoded.get("slewing") or state == MountState.SLEWING),
            "parked": parked,
            "at_home": report_at_home,
            "mechanical_position_authority": authority,
            "mechanical_safe": mechanical_safe,
            "logical_position": position,
            "sidereal_time": sidereal,
            "logical_axis_position": logical_axes,
            "derived_mount_axes": derived_axes,
            "pier_side": {
                "value": pier_side,
                "source": pier_source,
                "direct": direct_pier,
                "consistent": pier_consistent,
            },
            "ha_hours": round(ha_hours, 4) if ha_hours is not None else None,
            "meridian_distance_deg": round(ha_hours * 15.0, 4) if ha_hours is not None else None,
            **counterweight,
            "capture_pause_required": bool(counterweight.get("hard_limit_reached")),
            "tracking_stop_required": bool(
                (decoded.get("tracking") or state == MountState.TRACKING)
                and counterweight.get("hard_limit_reached")
            ),
            "motion_refused": motion_refused,
            "motion_refusal_reason": blockers[0] if blockers else None,
            "blockers": blockers,
            "context": context,
        }

    # ── SYNC-OVERRIDE REQ-ST-002 residual (partial upstream in v0.3.1) ────────

    def sync_onstep_time_location(
        self,
        *,
        lat: float,
        lon: float,
        alt_m: float = 0.0,
        utc_datetime: datetime | None = None,
        confirmed_by_user: bool = False,
    ) -> dict[str, object]:
        # Upstream v0.3.1 accepts confirmed_by_user but does not record the
        # trust source; set it post-hoc so safety clock locks clear.
        result = super().sync_onstep_time_location(
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            utc_datetime=utc_datetime,
            confirmed_by_user=confirmed_by_user,
        )
        if confirmed_by_user:
            self._safety_config = replace(
                self._safety_config, time_trust_source="user_confirmed"
            )
        return result

    # ── permanent SmartTScope wrappers ────────────────────────────────────────

    def ensure_time_location_synced(self) -> None:
        # REQ-ST-001 (permanent local glue): forward SmartTScope's own config
        # to upstream's sync_onstep_time_location().
        cfg = self._safety_config
        try:
            from ... import config as _cfg
            lat, lon = _cfg.OBSERVER_LAT, _cfg.OBSERVER_LON
        except (ImportError, AttributeError):
            lat, lon = cfg.observer_lat, cfg.observer_lon
        self.sync_onstep_time_location(
            lat=lat,
            lon=lon,
            alt_m=cfg.observer_alt_m,
            confirmed_by_user=True,
        )

    def get_sync_status(self) -> dict | None:
        """Read OnStep clock and site via LX200 commands and compare to Pi/config values.

        REQ-ST-008 (pending upstream adoption): meter-based location tolerance
        against the arcminute-rounded pushed site.
        """
        clock = self.read_onstep_clock()
        site = self.read_onstep_site()

        cfg_lat: float = self._safety_config.observer_lat
        cfg_lon: float = self._safety_config.observer_lon
        # LX200 ±DD*MM format stores only arcminute precision (~1852 m resolution).
        # Compare against what was actually pushed so location_ok=True after a sync.
        ref_lat: float = _lx200_round_degrees(cfg_lat)
        ref_lon: float = _lx200_round_degrees(cfg_lon)

        # getattr: tolerances live on SmartTScope's extended OnStepSafetyConfig;
        # fall back to its defaults when a bare upstream config was injected.
        time_tolerance_s: float = getattr(self._safety_config, "onstep_time_tolerance_s", 10.0)
        time_avail: bool = bool(clock.get("available"))
        time_delta_s: float | None = clock.get("delta_s") if time_avail else None
        time_ok: bool = (
            time_avail
            and time_delta_s is not None
            and time_delta_s <= time_tolerance_s
        )

        loc_tolerance_m: float = getattr(self._safety_config, "onstep_location_tolerance_m", 100.0)
        loc_avail: bool = bool(site.get("available"))
        onstep_lat: float | None = site.get("lat") if loc_avail else None
        onstep_lon: float | None = site.get("lon") if loc_avail else None
        lat_delta: float | None = (abs(onstep_lat - ref_lat) if onstep_lat is not None else None)
        lon_delta: float | None = (abs(onstep_lon - ref_lon) if onstep_lon is not None else None)
        location_delta_m: float | None = (
            _haversine_m(ref_lat, ref_lon, onstep_lat, onstep_lon)
            if onstep_lat is not None and onstep_lon is not None
            else None
        )
        loc_ok: bool = (
            loc_avail
            and location_delta_m is not None
            and location_delta_m <= loc_tolerance_m
        )

        return {
            "time_available":       time_avail,
            "time_delta_s":         time_delta_s,
            "time_threshold_s":     time_tolerance_s,
            "time_tolerance_s":     time_tolerance_s,
            "time_ok":              time_ok,
            "onstep_time_local":    clock.get("onstep_local"),   # ISO string; None when unavailable
            "master_time_local":    clock.get("system_local"),   # ISO string
            "location_available":   loc_avail,
            "onstep_lat":           onstep_lat,
            "onstep_lon":           onstep_lon,
            "cfg_lat":              cfg_lat,
            "cfg_lon":              cfg_lon,
            "ref_lat":              ref_lat,
            "ref_lon":              ref_lon,
            "lat_delta_deg":        lat_delta,
            "lon_delta_deg":        lon_delta,
            "location_delta_m":     location_delta_m,
            "location_tolerance_m": loc_tolerance_m,
            "location_ok":          loc_ok,
        }

    def get_position(self) -> MountPosition:
        # MountPort contract: return SmartTScope's MountPosition dataclass
        # (field-identical to upstream's; conversion keeps isinstance checks
        # against the local ports type working).
        pos = super().get_position()
        return MountPosition(ra=pos.ra, dec=pos.dec)

    def get_park_position(self) -> MountPosition | None:
        pos = super().get_park_position()
        return None if pos is None else MountPosition(ra=pos.ra, dec=pos.dec)

    def move(self, direction: str, move_ms: int) -> bool:
        # LOCAL-001 / REQ-1 (permanent local translation): MountPort.move()
        # routed through the SDK's public timed-axis API at center rate.
        #
        # SYNC-OVERRIDE REQ-ST-009 (user approval 2026-07-19): a deliberate
        # manual jog must work at confirmed mechanical HOME (terrestrial
        # workflow, M10-019/M10-028) — upstream _axis_motion() unconditionally
        # refuses on preflight["at_home"] with no bypass parameter. The window
        # flag below makes our motion_safety_preflight override report
        # at_home=False for exactly the two jog preflight commands while this
        # call is on the stack; every other preflight consumer (poller, goto,
        # tracking) keeps seeing the true at-home state, and all mechanical
        # blockers (motion_refused) stay fully active. Delete the flag and the
        # matching post-process in motion_safety_preflight() once upstream
        # ships a manual-jog mode (REQ-ST-009 issue).
        d = direction.lower()
        try:
            self._jog_bypass_active = True
            if d in ("e", "w", "east", "west"):
                result = self.move_ra_timed(d, move_ms, mode="center")
            elif d in ("n", "s", "north", "south"):
                result = self.move_dec_timed(d, move_ms, mode="center")
            else:
                _log.warning("OnStepMount.move(): invalid direction %r", direction)
                return False
        finally:
            self._jog_bypass_active = False
        return bool(result.ok)

    def set_park_position(self) -> bool:
        # REQ-2 (permanent MountPort adapter): maps the simple bool-returning
        # interface to upstream set_park_position_from_current().
        # allow_at_home=True because SmartTScope's park workflow sets
        # park = home position after a HOME slew.
        result = self.set_park_position_from_current(confirmed_safe=True, allow_at_home=True)
        return bool(result.ok)
