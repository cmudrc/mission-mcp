"""Execute the full mission analysis using NSEG or Aviary backend."""

from __future__ import annotations

import logging
from typing import Any

from ..physics.segments import SEGMENT_DISPATCH, SegmentResult
from ..session_manager import session_manager

logger = logging.getLogger(__name__)


def _run_nseg(session) -> dict[str, Any]:
    """Run all segments in order using the built-in NSEG physics."""
    vehicle = session.vehicle
    if not vehicle:
        return {"error": {"type": "ValidationError", "message": "Vehicle data not set. Call set_vehicle first."}}
    if not session.segments:
        return {"error": {"type": "ValidationError", "message": "No segments defined. Call set_segments first."}}

    weight = vehicle["weight_kg"]
    cd0 = vehicle["cd0"]
    k = vehicle["k"]
    wing_area_m2 = vehicle["wing_area_m2"]
    tsfc = vehicle["tsfc_1_per_s"]

    segment_results: list[dict[str, Any]] = []
    total_fuel = 0.0
    total_distance = 0.0
    total_time = 0.0

    for seg_def in session.segments:
        seg_type = seg_def["type"]
        handler = SEGMENT_DISPATCH.get(seg_type)
        if handler is None:
            return {"error": {"type": "RuntimeError", "message": f"Unknown segment type: {seg_type}"}}

        kwargs: dict[str, Any] = {
            "weight_kg": weight,
            "cd0": cd0,
            "k": k,
            "wing_area_m2": wing_area_m2,
            "tsfc_1_per_s": tsfc,
            "start_altitude_m": seg_def.get("start_altitude_m", 0),
            "end_altitude_m": seg_def.get("end_altitude_m", 0),
            "altitude_m": seg_def.get("end_altitude_m", seg_def.get("start_altitude_m", 0)),
            "mach": seg_def.get("mach", 0),
            "distance_m": seg_def.get("distance_m", 0),
            "duration_s": seg_def.get("duration_s", 0),
        }

        result: SegmentResult = handler(**kwargs)
        segment_results.append(result.to_dict())
        weight = result.end_weight_kg
        total_fuel += result.fuel_burned_kg
        total_distance += result.distance_m
        total_time += result.time_s

    return {
        "success": True,
        "backend": "nseg",
        "initial_weight_kg": vehicle["weight_kg"],
        "final_weight_kg": weight,
        "total_fuel_burned_kg": total_fuel,
        "fuel_burned_kg": total_fuel,
        "total_distance_m": total_distance,
        "total_distance_nm": total_distance / 1852.0,
        "total_time_s": total_time,
        "total_time_hr": total_time / 3600.0,
        "fuel_fraction": total_fuel / vehicle["weight_kg"],
        "segments": segment_results,
    }


def _run_aviary(session, timeout_seconds: int = 300) -> dict[str, Any]:
    """Run the mission using NASA Aviary trajectory optimisation."""
    from ..aviary.runner import (
        create_aviary_problem,
        extract_results,
        extract_trajectory,
        run_aviary,
    )

    mc = dict(session.mission_config)
    ap = dict(session.aircraft_params)

    logger.info("Creating Aviary problem (backend=aviary)...")
    try:
        prob = create_aviary_problem(aircraft_params=ap, mission_config=mc)
    except Exception as exc:
        logger.exception("Aviary setup failed")
        return {"error": {"type": "AviarySetupError", "message": str(exc)}}

    session.aviary_prob = prob

    logger.info("Running Aviary optimisation...")
    try:
        run_result = run_aviary(prob, timeout_seconds=timeout_seconds)
    except Exception as exc:
        logger.exception("Aviary simulation failed")
        return {"error": {"type": "AviaryRunError", "message": str(exc)}}

    converged = run_result["converged"]
    session.aviary_converged = converged

    results = extract_results(prob, converged)
    results.update(
        {
            "success": True,
            "runtime_seconds": run_result["runtime_seconds"],
            "iterations": run_result["iterations"],
            "timed_out": run_result.get("timed_out", False),
        }
    )

    smry = run_result.get("summary", {})
    results["total_fuel_burned_kg"] = smry.get("fuel_burned_kg")
    results["fuel_burned_kg"] = smry.get("fuel_burned_kg")

    try:
        trajectory = extract_trajectory(prob)
        session.trajectory = trajectory
    except Exception as exc:
        logger.warning("Trajectory extraction failed: %s", exc)

    return results


def run_mission(payload: dict[str, Any]) -> dict[str, Any]:
    """Run mission analysis with the configured vehicle and segments.

    Parameters
    ----------
    payload : dict
        ``session_id`` – mission session with vehicle and segments set.
        ``backend`` – ``"aviary"``, ``"nseg"``, or ``"auto"`` (default).
        ``timeout_seconds`` – wall-clock timeout for Aviary (default 300).
    """
    session_id = payload.get("session_id")
    if not session_id:
        return {"error": {"type": "ValidationError", "message": "session_id is required"}}

    session = session_manager.get(str(session_id))

    backend = payload.get("backend") or session.backend or "auto"
    timeout = int(payload.get("timeout_seconds", 300))

    if backend == "auto":
        from ..aviary import AVIARY_AVAILABLE

        backend = "aviary" if AVIARY_AVAILABLE else "nseg"
        logger.info("Auto-selected backend: %s", backend)

    if backend == "aviary":
        summary = _run_aviary(session, timeout_seconds=timeout)
    else:
        summary = _run_nseg(session)

    session.results = summary
    return summary
