"""Factory for the FastMCP server exposing mission analysis tools."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.server import FastMCP

from . import tools
from .aviary import AVIARY_AVAILABLE

__all__ = ["build_server"]

LOGGER = logging.getLogger(__name__)


def _register_tools(server: FastMCP) -> None:
    """Attach mission tool implementations to a FastMCP instance."""

    @server.tool(
        name="create_mission",
        description="Create a new mission analysis session.",
        tags={"mission", "session"},
    )
    def create_mission_tool(name: str = "unnamed_mission") -> dict[str, Any]:
        return tools.create_mission({"name": name})

    @server.tool(
        name="close_mission",
        description="Close a mission session and free resources.",
        tags={"mission", "session"},
    )
    def close_mission_tool(session_id: str) -> dict[str, Any]:
        return tools.close_mission({"session_id": session_id})

    @server.tool(
        name="set_vehicle",
        description=(
            "Set vehicle parameters: weight_kg, wing_area_m2, cd0, k "
            "(induced drag factor), tsfc_1_per_s, max_thrust_n."
        ),
        tags={"mission", "vehicle"},
    )
    def set_vehicle_tool(
        session_id: str,
        weight_kg: float,
        wing_area_m2: float,
        cd0: float,
        k: float,
        tsfc_1_per_s: float,
        max_thrust_n: float = 0.0,
        cl_max: float = 2.0,
    ) -> dict[str, Any]:
        return tools.set_vehicle({
            "session_id": session_id,
            "weight_kg": weight_kg,
            "wing_area_m2": wing_area_m2,
            "cd0": cd0,
            "k": k,
            "tsfc_1_per_s": tsfc_1_per_s,
            "max_thrust_n": max_thrust_n,
            "cl_max": cl_max,
        })

    @server.tool(
        name="set_segments",
        description=(
            "Define the ordered list of flight segments. Each segment has a type "
            "(taxi/takeoff/climb/cruise/descent/approach/landing) and parameters."
        ),
        tags={"mission", "segments"},
    )
    def set_segments_tool(
        session_id: str,
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return tools.set_segments({"session_id": session_id, "segments": segments})

    @server.tool(
        name="configure_mission",
        description=(
            "Set mission profile: range_nmi, num_passengers, cruise_mach, "
            "cruise_altitude_ft, optimizer_max_iter. Also selects backend "
            "(aviary / nseg / auto)."
        ),
        tags={"mission", "configuration"},
    )
    def configure_mission_tool(
        session_id: str,
        range_nmi: float | None = None,
        num_passengers: int | None = None,
        cruise_mach: float | None = None,
        cruise_altitude_ft: float | None = None,
        optimizer_max_iter: int | None = None,
        backend: str | None = None,
    ) -> dict[str, Any]:
        p: dict[str, Any] = {"session_id": session_id}
        if range_nmi is not None:
            p["range_nmi"] = range_nmi
        if num_passengers is not None:
            p["num_passengers"] = num_passengers
        if cruise_mach is not None:
            p["cruise_mach"] = cruise_mach
        if cruise_altitude_ft is not None:
            p["cruise_altitude_ft"] = cruise_altitude_ft
        if optimizer_max_iter is not None:
            p["optimizer_max_iter"] = optimizer_max_iter
        if backend is not None:
            p["backend"] = backend
        return tools.configure_mission(p)

    @server.tool(
        name="run_mission",
        description=(
            "Execute mission analysis. Uses Aviary (NASA trajectory optimizer) "
            "when available, otherwise falls back to built-in NSEG physics."
        ),
        tags={"mission", "execution"},
    )
    def run_mission_tool(
        session_id: str,
        backend: str | None = None,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        p: dict[str, Any] = {"session_id": session_id, "timeout_seconds": timeout_seconds}
        if backend:
            p["backend"] = backend
        return tools.run_mission(p)

    @server.tool(
        name="get_results",
        description="Retrieve results from the last mission analysis run.",
        tags={"mission", "results"},
    )
    def get_results_tool(session_id: str) -> dict[str, Any]:
        return tools.get_results({"session_id": session_id})

    @server.tool(
        name="get_trajectory",
        description=(
            "Return trajectory timeseries (altitude, Mach, mass, throttle, "
            "drag vs time) from an Aviary-backed run. NSEG runs return "
            "per-segment summaries."
        ),
        tags={"mission", "trajectory"},
    )
    def get_trajectory_tool(
        session_id: str,
        variables: list[str] | None = None,
    ) -> dict[str, Any]:
        p: dict[str, Any] = {"session_id": session_id}
        if variables:
            p["variables"] = variables
        return tools.get_trajectory(p)

    @server.tool(
        name="check_constraints",
        description=(
            "Evaluate pass/fail for user-defined constraints on mission results. "
            "Supports <=, >=, == operators on fuel_burned_kg, gtow_kg, etc."
        ),
        tags={"mission", "constraints"},
    )
    def check_constraints_tool(
        session_id: str,
        constraints: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return tools.check_constraints({
            "session_id": session_id,
            "constraints": constraints,
        })


def build_server() -> FastMCP:
    """Construct a FastMCP server with all mission tools registered."""
    backend_note = "Aviary available" if AVIARY_AVAILABLE else "NSEG only (install Aviary for trajectory optimization)"
    server = FastMCP(
        name="mission-mcp",
        instructions=(
            "Mission analysis MCP with dual backends. "
            "Primary: NASA Aviary (trajectory optimization, fuel burn, mass tracking). "
            "Fallback: NSEG segment-based physics (Breguet range). "
            f"Current: {backend_note}. "
            "Create a mission, configure parameters, then run analysis."
        ),
    )
    _register_tools(server)
    LOGGER.debug("FastMCP mission server configured (aviary=%s)", AVIARY_AVAILABLE)
    return server
