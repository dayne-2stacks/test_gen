from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .boolean_sat import SatAtpg
from .fault_collapsing import CollapseResult, FaultClass, FaultCollapser
from .fault_simulation import FaultSimulationReport, FaultSimulator
from .d_algorithm import DAlgorithmEngine
from .podem import PodemEngine
from .netlist_parser import NetlistParseError, NetlistParser, parse_netlist


# Exported core engine classes and helpers for ATG
__all__ = [
    "SatAtpg",                # SAT-based ATPG engine
    "FaultCollapser",         # Fault collapsing engine
    "CollapseResult",         # Result of fault collapsing
    "FaultClass",             # Fault equivalence class
    "FaultSimulator",         # Fault simulation engine
    "FaultSimulationReport",  # Fault simulation report
    "DAlgorithmEngine",       # D-Algorithm ATPG engine
    "PodemEngine",            # PODEM ATPG engine
    "NetlistParser",          # Netlist parser
    "NetlistParseError",      # Netlist parse error
    "parse_netlist",          # Netlist parsing function
    "log_stage_output",       # Output logging helper
]

# Paths for project and output directories
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_ROOT = _PROJECT_ROOT / "outputs"

def _sanitize_stage_name(name: str) -> str:
    """
    Splits stage name to store output
    """
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)

def _circuit_output_dir(circuit_source: str | Path) -> Path:
    """
    Creates dir for circuit outputs
    """
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
    """
    Log outputs of each stage
    """
    _OUTPUT_ROOT.mkdir(exist_ok=True)
    stage_file = _circuit_output_dir(circuit_source) / (
        f"{_sanitize_stage_name(stage_name)}.txt"
    )
    stage_file.write_text("\n".join(str(line) for line in lines) + "\n", encoding="utf-8")
    return stage_file
