from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .boolean_sat import SatAtpg
from .fault_collapsing import CollapseResult, FaultClass, FaultCollapser
from .fault_simulation import FaultSimulationReport, FaultSimulator, SimulationMode
from .d_algorithm import DAlgorithmEngine
from .podem import PodemEngine
from .netlist_parser import NetlistParseError, NetlistParser, parse_netlist

__all__ = [
    "SatAtpg",
    "FaultCollapser",
    "CollapseResult",
    "FaultClass",
    "FaultSimulator",
    "SimulationMode",
    "FaultSimulationReport",
    "DAlgorithmEngine",
    "PodemEngine",
    "NetlistParser",
    "NetlistParseError",
    "parse_netlist",
    "log_stage_output",
]

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_ROOT = _PROJECT_ROOT / "outputs"


def _sanitize_stage_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)


def _circuit_output_dir(circuit_source: str | Path) -> Path:
    circuit_path = Path(circuit_source)
    circuit_name = circuit_path.name or circuit_path.stem or "circuit"
    output_dir = _OUTPUT_ROOT / circuit_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def log_stage_output(
    circuit_source: str | Path,
    stage_name: str,
    lines: Iterable[str],
) -> Path:
    """Write a stage summary to outputs/<circuit>/<stage_name>.txt."""
    _OUTPUT_ROOT.mkdir(exist_ok=True)
    stage_file = _circuit_output_dir(circuit_source) / (
        f"{_sanitize_stage_name(stage_name)}.txt"
    )
    stage_file.write_text("\n".join(str(line) for line in lines) + "\n", encoding="utf-8")
    return stage_file
