"""Shared-CPACS adapter for the Mission MCP.

Reads vehicle data and aerodynamic/engine results from the CPACS XML,
runs mission analysis (Aviary or NSEG), and writes mission results
back into ``//vehicles/aircraft/model/analysisResults/mission``.
"""

from __future__ import annotations

import logging
import math
from typing import Any
from xml.etree import ElementTree as ET

from mission_mcp.aviary import AVIARY_AVAILABLE
from mission_mcp.tools.create_mission import close_mission, create_mission
from mission_mcp.tools.run_mission import run_mission
from mission_mcp.tools.set_segments import set_segments
from mission_mcp.tools.set_vehicle import set_vehicle

logger = logging.getLogger(__name__)


def read_from_cpacs(
    cpacs_xml: str,
    mission_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract vehicle + aero + engine data from CPACS for mission analysis."""
    root = ET.fromstring(cpacs_xml)

    ref_area_el = root.find(".//vehicles/aircraft/model/reference/area")
    ref_area = float(ref_area_el.text) if ref_area_el is not None and ref_area_el.text else 122.4

    cd = 0.025
    aero_cd = root.find(".//vehicles/aircraft/model/analysisResults/aero/coefficients/CD")
    if aero_cd is not None and aero_cd.text:
        cd = float(aero_cd.text)

    cd0_el = root.find(".//vehicles/aircraft/model/analysisResults/aero/coefficients/CD0")
    cd0 = float(cd0_el.text) if cd0_el is not None and cd0_el.text else 0.020

    cl_el = root.find(".//vehicles/aircraft/model/analysisResults/aero/coefficients/CL")
    cl = float(cl_el.text) if cl_el is not None and cl_el.text else 0.5
    k = (cd - cd0) / (cl * cl) if cl > 0.01 else 0.04

    tsfc_el = root.find(".//vehicles/engines/engine/analysis/mcpResults/TSFC_1_per_s")
    tsfc = float(tsfc_el.text) if tsfc_el is not None and tsfc_el.text else 1.7e-5

    fn_el = root.find(".//vehicles/engines/engine/analysis/mcpResults/Fn_N")
    max_thrust = float(fn_el.text) if fn_el is not None and fn_el.text else 120000.0

    # Wing geometry for Aviary
    wing = root.find(".//vehicles/aircraft/model/wings/wing")
    wing_area = ref_area
    aspect_ratio = None
    sweep = None
    taper_ratio = None
    if wing is not None:
        ar_el = wing.find("aspectRatio")
        if ar_el is not None and ar_el.text:
            aspect_ratio = float(ar_el.text)
        sw_el = wing.find("sweep/angle")
        if sw_el is not None and sw_el.text:
            sweep = float(sw_el.text)
        tr_el = wing.find("taperRatio")
        if tr_el is not None and tr_el.text:
            taper_ratio = float(tr_el.text)

    # Fuselage for Aviary
    fus = root.find(".//vehicles/aircraft/model/fuselages/fuselage")
    fus_length = None
    if fus is not None:
        fl_el = fus.find("length")
        if fl_el is not None and fl_el.text:
            fus_length = float(fl_el.text)

    mp = mission_profile or {}

    return {
        "ref_area_m2": ref_area,
        "cd0": cd0,
        "k": round(k, 6),
        "tsfc_1_per_s": tsfc,
        "max_thrust_n": max_thrust,
        "weight_kg": mp.get("weight_kg", 78000.0),
        "cruise_mach": mp.get("cruise_mach", 0.78),
        "cruise_altitude_m": mp.get("cruise_altitude_m", 10668.0),
        "range_m": mp.get("range_m", 3_000_000.0),
        "segments": mp.get("segments"),
        # Aviary-specific geometry
        "wing_area_m2": wing_area,
        "aspect_ratio": aspect_ratio,
        "sweep_deg": sweep,
        "taper_ratio": taper_ratio,
        "fuselage_length_m": fus_length,
        # Aviary mission params
        "range_nmi": mp.get("range_nmi", mp.get("range_m", 3_000_000.0) / 1852.0),
        "num_passengers": mp.get("num_passengers", 162),
        "cruise_altitude_ft": mp.get(
            "cruise_altitude_ft",
            mp.get("cruise_altitude_m", 10668.0) * 3.28084,
        ),
    }


def _build_default_segments(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a standard taxi-takeoff-climb-cruise-descent-approach-landing profile."""
    alt = inputs["cruise_altitude_m"]
    mach = inputs["cruise_mach"]
    return [
        {"type": "taxi", "duration_s": 300},
        {"type": "takeoff"},
        {"type": "climb", "start_altitude_m": 0, "end_altitude_m": alt, "mach": min(mach, 0.6)},
        {"type": "cruise", "start_altitude_m": alt, "end_altitude_m": alt,
         "mach": mach, "distance_m": inputs["range_m"]},
        {"type": "descent", "start_altitude_m": alt, "end_altitude_m": 600, "mach": min(mach, 0.5)},
        {"type": "approach", "start_altitude_m": 600},
        {"type": "landing"},
    ]


def _build_aviary_params(inputs: dict[str, Any]) -> dict[str, Any]:
    """Map CPACS geometry to Aviary parameter names."""
    params: dict[str, Any] = {}
    if inputs.get("wing_area_m2"):
        params["Aircraft.Wing.AREA"] = inputs["wing_area_m2"]
    if inputs.get("aspect_ratio"):
        params["Aircraft.Wing.ASPECT_RATIO"] = inputs["aspect_ratio"]
    if inputs.get("sweep_deg"):
        params["Aircraft.Wing.SWEEP"] = inputs["sweep_deg"]
    if inputs.get("taper_ratio"):
        params["Aircraft.Wing.TAPER_RATIO"] = inputs["taper_ratio"]
    if inputs.get("fuselage_length_m"):
        params["Aircraft.Fuselage.LENGTH"] = inputs["fuselage_length_m"]
    return params


def write_to_cpacs(cpacs_xml: str, results: dict[str, Any]) -> str:
    """Write mission results into ``//vehicles/aircraft/model/analysisResults/mission``."""
    root = ET.fromstring(cpacs_xml)

    model = root.find(".//vehicles/aircraft/model")
    if model is None:
        model = _ensure_path(root, "vehicles/aircraft/model")

    ar = model.find("analysisResults")
    if ar is None:
        ar = ET.SubElement(model, "analysisResults")

    existing = ar.find("mission")
    if existing is not None:
        ar.remove(existing)

    m_el = ET.SubElement(ar, "mission")
    backend = results.get("backend", "nseg")
    ET.SubElement(m_el, "backend").text = backend
    ET.SubElement(m_el, "success").text = str(results.get("success", False)).lower()

    fuel = results.get("total_fuel_burned_kg") or results.get("fuel_burned_kg", 0.0)
    ET.SubElement(m_el, "totalFuelBurnedKg").text = str(fuel)

    if backend == "aviary":
        for tag, key in [
            ("gtowKg", "gtow_kg"),
            ("wingMassKg", "wing_mass_kg"),
            ("reserveFuelKg", "reserve_fuel_kg"),
            ("zeroFuelWeightKg", "zero_fuel_weight_kg"),
            ("fuelBurnedKg", "fuel_burned_kg"),
            ("converged", "converged"),
            ("runtimeSeconds", "runtime_seconds"),
            ("iterations", "iterations"),
        ]:
            val = results.get(key)
            if val is not None:
                ET.SubElement(m_el, tag).text = str(val)
    else:
        ET.SubElement(m_el, "initialWeightKg").text = str(results.get("initial_weight_kg", 0.0))
        ET.SubElement(m_el, "finalWeightKg").text = str(results.get("final_weight_kg", 0.0))
        ET.SubElement(m_el, "totalDistanceM").text = str(results.get("total_distance_m", 0.0))
        ET.SubElement(m_el, "totalDistanceNm").text = str(results.get("total_distance_nm", 0.0))
        ET.SubElement(m_el, "totalTimeS").text = str(results.get("total_time_s", 0.0))
        ET.SubElement(m_el, "totalTimeHr").text = str(results.get("total_time_hr", 0.0))
        ET.SubElement(m_el, "fuelFraction").text = str(results.get("fuel_fraction", 0.0))

        segs_el = ET.SubElement(m_el, "segments")
        for seg in results.get("segments", []):
            seg_el = ET.SubElement(segs_el, "segment")
            ET.SubElement(seg_el, "type").text = seg.get("segment_type", "unknown")
            ET.SubElement(seg_el, "fuelBurnedKg").text = str(seg.get("fuel_burned_kg", 0.0))
            ET.SubElement(seg_el, "distanceM").text = str(seg.get("distance_m", 0.0))
            ET.SubElement(seg_el, "timeS").text = str(seg.get("time_s", 0.0))

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def run_adapter(
    cpacs_xml: str,
    mission_profile: dict[str, Any] | None = None,
    backend: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Full read -> process -> write cycle for the Mission domain.

    Returns (updated_cpacs_xml, summary_dict).
    """
    inputs = read_from_cpacs(cpacs_xml, mission_profile)

    effective_backend = backend or ("aviary" if AVIARY_AVAILABLE else "nseg")

    if effective_backend == "aviary":
        results = _run_with_aviary(inputs)
    else:
        results = _run_with_nseg(inputs)

    if results.get("success"):
        updated_xml = write_to_cpacs(cpacs_xml, results)
    else:
        updated_xml = cpacs_xml

    return updated_xml, results


def _run_with_aviary(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run mission using the Aviary trajectory optimizer."""
    from mission_mcp.aviary.runner import (
        create_aviary_problem,
        extract_results,
        extract_trajectory,
        run_aviary,
    )

    aircraft_params = _build_aviary_params(inputs)
    mission_config = {
        "range_nmi": inputs.get("range_nmi", 1500),
        "num_passengers": inputs.get("num_passengers", 162),
        "cruise_mach": inputs.get("cruise_mach", 0.785),
        "cruise_altitude_ft": inputs.get("cruise_altitude_ft", 35000),
        "optimizer_max_iter": 200,
    }

    logger.info(
        "Running Aviary mission: range=%d nmi, M=%.3f, alt=%d ft",
        mission_config["range_nmi"],
        mission_config["cruise_mach"],
        mission_config["cruise_altitude_ft"],
    )

    try:
        prob = create_aviary_problem(
            aircraft_params=aircraft_params,
            mission_config=mission_config,
        )
        run_result = run_aviary(prob, timeout_seconds=300)
    except Exception as exc:
        logger.warning("Aviary failed, falling back to NSEG: %s", exc)
        return _run_with_nseg_from_inputs(inputs)

    converged = run_result["converged"]
    results = extract_results(prob, converged)
    results.update({
        "success": True,
        "runtime_seconds": run_result["runtime_seconds"],
        "iterations": run_result["iterations"],
        "timed_out": run_result.get("timed_out", False),
    })

    smry = run_result.get("summary", {})
    results["total_fuel_burned_kg"] = smry.get("fuel_burned_kg")
    results["fuel_burned_kg"] = smry.get("fuel_burned_kg")

    try:
        traj = extract_trajectory(prob)
        results["trajectory_points"] = traj.get("num_points", 0)
    except Exception:
        pass

    return results


def _run_with_nseg(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run mission using the built-in NSEG segment physics."""
    return _run_with_nseg_from_inputs(inputs)


def _run_with_nseg_from_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """NSEG execution using the MCP tool functions."""
    session = create_mission({"name": "cpacs_mission"})
    sid = session["session_id"]

    try:
        set_vehicle({
            "session_id": sid,
            "weight_kg": inputs["weight_kg"],
            "wing_area_m2": inputs["ref_area_m2"],
            "cd0": inputs["cd0"],
            "k": inputs["k"],
            "tsfc_1_per_s": inputs["tsfc_1_per_s"],
            "max_thrust_n": inputs["max_thrust_n"],
        })

        segments = inputs.get("segments") or _build_default_segments(inputs)
        set_segments({"session_id": sid, "segments": segments})

        results = run_mission({"session_id": sid, "backend": "nseg"})
    finally:
        close_mission({"session_id": sid})

    return results


def _ensure_path(root: ET.Element, path: str) -> ET.Element:
    current = root
    for part in path.split("/"):
        child = current.find(part)
        if child is None:
            child = ET.SubElement(current, part)
        current = child
    return current
