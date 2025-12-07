# Initializes the core engine package for fault simulation, collapsing, SAT solving, and parsing.
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .boolean_sat import SatAtpg
from .fault_collapsing import CollapseResult, FaultClass, FaultCollapser
from .fault_simulation import FaultSimulationReport, FaultSimulator, SimulationMode
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
    "SimulationMode",         # Simulation mode enum
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
    Sanitize a stage name for use in output filenames.
    Replaces non-alphanumeric characters with underscores.
    """
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)

def _circuit_output_dir(circuit_source: str | Path) -> Path:
    """
    Get the output directory for a given circuit source.
    Creates the directory if it does not exist.
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
    Write a stage summary to outputs/<circuit>/<stage_name>.txt.
    Args:
        circuit_source: Source file for the circuit.
        stage_name: Name of the processing stage.
        lines: Iterable of lines to write.
    Returns:
        Path to the output file written.
    """
    _OUTPUT_ROOT.mkdir(exist_ok=True)
    stage_file = _circuit_output_dir(circuit_source) / (
        f"{_sanitize_stage_name(stage_name)}.txt"
    )
    stage_file.write_text("\n".join(str(line) for line in lines) + "\n", encoding="utf-8")
    return stage_file
