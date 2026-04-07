# mission-mcp

[![CI](https://github.com/cmudrc/mission-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/cmudrc/mission-mcp/actions/workflows/ci.yml)
[![OVS](https://github.com/cmudrc/mission-mcp/actions/workflows/ovs.yml/badge.svg)](https://github.com/cmudrc/mission-mcp/actions/workflows/ovs.yml)

A **Model Context Protocol (MCP)** server for aircraft mission analysis with a
dual-backend architecture:

| Backend | Description |
|---------|-------------|
| **Aviary** (primary) | NASA's open-source trajectory optimizer built on OpenMDAO + Dymos. Gradient-based optimization of climb/cruise/descent with fuel burn, GTOW, and detailed timeseries. |
| **NSEG** (fallback) | Built-in segment physics engine using Breguet range, ISA atmosphere, and drag-polar models. Works for any aircraft without external solvers. |

The server automatically selects Aviary when installed and compatible with the
aircraft geometry, falling back to NSEG otherwise.

## Tools (9)

| Tool | Description |
|------|-------------|
| `create_mission` | Start a new mission analysis session |
| `close_mission` | Close a session and free resources |
| `set_vehicle` | Set vehicle parameters (weight, wing area, CD0, k, TSFC) |
| `set_segments` | Define flight segment sequence (NSEG backend) |
| `configure_mission` | Set range, passengers, cruise Mach/altitude, backend |
| `run_mission` | Execute analysis — Aviary or NSEG |
| `get_results` | Retrieve results from the last run |
| `get_trajectory` | Get timeseries trajectory data (Aviary) or per-segment summaries (NSEG) |
| `check_constraints` | Evaluate pass/fail for user-defined constraints |

## Quick start

```bash
# Install base (NSEG only)
pip install -e .

# Install with Aviary
pip install -e ".[aviary]"

# Run the MCP server
mission-mcp
```

## Shared-CPACS Integration

This MCP includes a **CPACS adapter** (`src/mission_mcp/cpacs_adapter.py`) that
bridges the mission analysis to the shared-CPACS aircraft analysis pipeline.

### What it does

The adapter reads aircraft geometry and aerodynamic/engine results from CPACS
(produced by TiGL, SU2, and pyCycle), runs trajectory optimization via Aviary
or segment analysis via NSEG, and writes mission results (fuel burn, GTOW,
trajectory data) back to CPACS.

| Direction | XPaths |
|-----------|--------|
| **Reads** | `.//vehicles/aircraft/model/reference`, `.//analysisResults/aero`, `.//vehicles/engines/engine/analysis/mcpResults` |
| **Writes** | `.//vehicles/aircraft/model/analysisResults/mission` (backend, fuel_burned_kg, gtow_kg, wing_mass_kg, converged, trajectory_points, range, segments) |

### Running as part of the pipeline

```bash
python pipeline/shared_cpacs_orchestrator.py D150_v30.xml --mcps tigl su2 pycycle mission
```

See [cmudrc/aircraft-analysis](https://github.com/cmudrc/aircraft-analysis) for
full pipeline documentation.

### Related MCP servers

| MCP | Repository |
|-----|-----------|
| TiGL (geometry) | [cmudrc/tigl-mcp](https://github.com/cmudrc/tigl-mcp) |
| SU2 (CFD aerodynamics) | [cmudrc/su2-mcp](https://github.com/cmudrc/su2-mcp) |
| pyCycle (engine cycle) | [cmudrc/pycycle-mcp](https://github.com/cmudrc/pycycle-mcp) |

## Dependencies

### Required

- Python >= 3.12
- fastmcp ~= 2.13.1
- pydantic >= 2.6.0
- numpy >= 1.26

### Optional (Aviary backend)

> **Critical**: Version pinning is required for Aviary compatibility.

- `aviary == 0.9.10`
- `openmdao == 3.36.0`
- `dymos == 1.13.1`

## Contributing

Contribution guidelines live in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE)
