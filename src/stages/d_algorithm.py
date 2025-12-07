from pathlib import Path
from typing import Dict, List, Optional, Sequence

from core.d_algorithm import DAlgorithmEngine
from models import Fault
from utils import AtpgEngine, TestVector


def _prompt_fault(circuit, collapse_result) -> Optional[Fault]:
    """
    Prompt the user to select a fault from the collapsed fault set.
    """
    # Display a preview of collapsed faults for doc
    total = len(collapse_result.collapsed_faults)
    preview = ", ".join(str(f) for f in collapse_result.collapsed_faults[:8])
    if preview:
        print(f"Example collapsed faults ({min(total, 8)}/{total}): {preview}")
    # Prompt user for faults to test
    while True:
        raw = input(
            "Enter target fault as '<net>[->sink] <stuck_at>' or 'q' to cancel: "
        ).strip()
        if not raw:
            print("Please provide a net name and stuck-at value.")
            continue
        # Handle quit option
        if raw.lower() in {"q", "quit"}:
            return None
        parts = raw.split()
        # If not a valid net and stuck-at format retry
        if len(parts) != 2 or parts[1] not in {"0", "1"}:
            print("Format must be '<net>[->sink] <0|1>'.")
            continue
        #  get the net and stuck-at values to test
        net_token, stuck_token = parts
        stuck = int(stuck_token)
        sink = None
        # handle fanouts
        if "->" in net_token:
            net, sink = net_token.split("->", 1)
        else:
            net = net_token
        # validate net and sink existence
        if net not in circuit.nets:
            print(f"Net '{net}' not found in the circuit.")
            continue
        if sink and sink not in circuit.nets[net].sinks:
            print(f"Sink gate '{sink}' is not driven by net '{net}'.")
            continue
        # create the fault and check if it's in the collapsed set
        fault = Fault(net=net, stuck_at=stuck, sink=sink or None)
        representative = collapse_result.fault_to_representative.get(fault)
        if representative is None:
            print("Fault not present in the collapsed set; please choose another.")
            continue
        return representative


def _format_vector(vector: Optional[Dict[str, int]], primary_inputs) -> str:
    """Format a test vector for display or output."""
    if vector is None:
        return "none"
    ordered = [(pi, vector.get(pi, 0)) for pi in primary_inputs]
    return ", ".join(f"{pi}={val}" for pi, val in ordered)


def _write_test_vectors(circuit, vectors: Sequence[TestVector]) -> Path:
    """ Write test vectors to an output file and return the file path. """
    source = getattr(circuit, "source", None) or "circuit"
    circuit_name = Path(source).name
    root_dir = Path(__file__).resolve().parents[2]
    output_dir = root_dir / "outputs" / circuit_name / "d_algorithm"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test_vectors.out"

    # For each test vector, format and write to file
    lines: List[str] = []
    for idx, vector in enumerate(vectors, 1):
        formatted_vector = _format_vector(vector.vector, circuit.primary_inputs)
        detected_sorted = sorted(
            vector.detected_faults, key=lambda f: (f.net, f.sink or "", f.stuck_at)
        )
        detected_str = ", ".join(str(f) for f in detected_sorted) or "none"
        lines.append(f"Vector {idx}: target={vector.fault}")
        lines.append(f"Inputs: {formatted_vector}")
        lines.append(f"Detected faults ({len(detected_sorted)}): {detected_str}")
        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def _render_test_vector(circuit, test_vector: TestVector) -> None:
    """Display a test vector result to the user."""
    if test_vector.vector is None:
        print(f"No D-Algorithm test vector found for {test_vector.fault}.")
        return
    # Display the formatted vector and detected faults to console
    formatted_vector = _format_vector(test_vector.vector, circuit.primary_inputs)
    detected_sorted = sorted(
        test_vector.detected_faults, key=lambda f: (f.net, f.sink or "", f.stuck_at)
    )
    detected_str = ", ".join(str(f) for f in detected_sorted) or "none"
    print(f"Found a D-Algorithm test vector for {test_vector.fault}:")
    print(f"  {formatted_vector}")
    print(f"  Detected faults ({len(detected_sorted)}): {detected_str}")


def _collect_manual_faults(circuit, collapse_result) -> List[Fault]:
    """Prompt user to select multiple faults for manual D-Algorithm testing."""
    # Collect faults interactively from the user
    faults: List[Fault] = []
    while True:
        fault = _prompt_fault(circuit, collapse_result)
        if fault is None:
            break
        faults.append(fault)
        # Ask if user wants to add another fault
        again = input("Target another collapsed fault? (y/n): ").strip().lower()
        if again not in {"y", "yes"}:
            break
    return faults


def _run_manual_mode(engine: AtpgEngine, circuit, collapse_result):
    """Run D-Algorithm in manual mode based on user-selected faults."""
    faults = _collect_manual_faults(circuit, collapse_result)
    # If no faults were selected, cancel the operation
    if not faults:
        print("D-Algorithm cancelled.")
        return None
    # run manual ATPG on selected faults
    results = engine.manual(faults)
    for test_vector in results:
        _render_test_vector(circuit, test_vector)
    # Write results to file
    output_path = _write_test_vectors(circuit, results)
    print(f"Wrote {len(results)} D-Algorithm test vector(s) to {output_path}")
    return {"mode": "manual", "vectors": results, "output_path": output_path}


def _run_automatic_mode(engine: AtpgEngine, circuit):
    """Run D-Algorithm in automatic mode across all collapsed faults."""
    print("Running D-Algorithm in automatic mode across collapsed faults...")
    # run automatic ATPG
    results = engine.automatic()
    # coount number of test vectors found and unique detected faults
    vectors_found = sum(1 for vector in results if vector.vector is not None)
    detected_faults = set()
    for vector in results:
        detected_faults.update(vector.detected_faults)
    # Output results
    print(f"Generated vectors for {vectors_found}/{len(results)} target faults.")
    print(f"Unique detected faults: {len(detected_faults)}")
    output_path = _write_test_vectors(circuit, results)
    print(f"Wrote {len(results)} D-Algorithm test vector(s) to {output_path}")
    return {
        "mode": "automatic",
        "vectors": results,
        "output_path": output_path,
        "detected_faults": tuple(detected_faults),
        "vectors_found": vectors_found,
    }


def run_d_algorithm(circuit, collapse_result):
    """ Main entry point for running the D-Algorithm stage. """
    if circuit is None:
        print("Please parse a circuit before running the D-Algorithm.")
        return None
    if collapse_result is None:
        print("Please perform fault collapsing before running the D-Algorithm.")
        return None
    # run D algo with the built in ATTPG class
    engine = AtpgEngine(circuit, collapse_result, DAlgorithmEngine)

    # Select between manual and automatic modes
    while True:
        print("\nD-Algorithm options:")
        print("  [1] Manual: choose specific collapsed fault(s)")
        print("  [2] Automatic: cover all collapsed faults")
        print("  [q] Cancel and return to the main menu")
        choice = input("Select a D-Algorithm mode: ").strip().lower()
        if choice == "1":
            return _run_manual_mode(engine, circuit, collapse_result)
        if choice == "2":
            return _run_automatic_mode(engine, circuit)
        if choice in {"q", "quit"}:
            print("D-Algorithm cancelled.")
            return None
        print("Invalid selection. Please type '1', '2', or 'q'.")
