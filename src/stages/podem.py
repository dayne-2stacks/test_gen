from pathlib import Path
from typing import Dict, List, Optional, Sequence

from models import Fault
from core.podem import PodemEngine
from utils import AtpgEngine, TestVector



def _prompt_fault(circuit, collapse_result):
    """
    Prompt the user to select a fault from the collapsed fault set.
    """
    # Get the number of collapsed faults and show a preview of the first 8
    total = len(collapse_result.collapsed_faults)
    preview = ", ".join(str(f) for f in collapse_result.collapsed_faults[:8])
    if preview:
        print(f"Example collapsed faults ({min(total, 8)}/{total}): {preview}")
    # Prompt user for faults to test with error handling and quitting 
    while True:
        raw = input(
            "Enter target fault as '<net>[->sink] <stuck_at>' or 'q' to cancel: "
        ).strip()
        if not raw:
            print("Please provide a net name and stuck-at value.")
            continue
        if raw.lower() in {"q", "quit"}:
            return None
        # extract net and stuck-at values
        parts = raw.split()
        if len(parts) != 2 or parts[1] not in {"0", "1"}:
            print("Format must be '<net>[->sink] <0|1>'.")
            continue
        net_token, stuck_token = parts
        stuck = int(stuck_token)
        sink = None
        # Handle fanouts
        if "->" in net_token:
            net, sink = net_token.split("->", 1)
        else:
            net = net_token
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


def _format_vector(vector: Optional[Dict[str, int]], primary_inputs: Sequence[str]) -> str:
    # Format a test vector for display or output.
    if vector is None:
        return "none"
    ordered = [(pi, vector.get(pi, 0)) for pi in primary_inputs]
    return ", ".join(f"{pi}={val}" for pi, val in ordered)


def _render_test_vector(circuit, test_vector: TestVector):
    # Display a test vector result to the user.
    if test_vector.vector is None:
        print(f"No PODEM test vector found for {test_vector.fault}.")
        return
    # Format and display the test vector and detected faults
    formatted = _format_vector(test_vector.vector, circuit.primary_inputs)
    detected_sorted = sorted(
        test_vector.detected_faults, key=lambda f: (f.net, f.sink or "", f.stuck_at)
    )
    detected_str = ", ".join(str(f) for f in detected_sorted) or "none"
    print(f"Found PODEM test vector for {test_vector.fault}:")
    print(f"  {formatted}")
    print(f"  Detected faults ({len(detected_sorted)}): {detected_str}")


def _collect_manual_faults(circuit, collapse_result) -> List[Fault]:
    # Collect multiple faults from user input until they choose to stop.
    faults: List[Fault] = []
    while True:
        fault = _prompt_fault(circuit, collapse_result)
        if fault is None:
            break
        faults.append(fault)
        again = input("Target another collapsed fault? (y/n): ").strip().lower()
        if again not in {"y", "yes"}:
            break
    return faults


def _write_test_vectors(circuit, vectors: Sequence[TestVector]) -> Path:
    """ Write test vectors to an output file and return the file path. """
    source = getattr(circuit, "source", None) or "circuit"
    circuit_name = Path(source).name
    root_dir = Path(__file__).resolve().parents[2]
    output_dir = root_dir / "outputs" / circuit_name / "podem"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test_vectors.out"

    # For each test vector, format and write to file
    lines: List[str] = []
    for idx, vector in enumerate(vectors, 1):
        formatted = _format_vector(vector.vector, circuit.primary_inputs)
        detected_sorted = sorted(
            vector.detected_faults, key=lambda f: (f.net, f.sink or "", f.stuck_at)
        )
        detected_str = ", ".join(str(f) for f in detected_sorted) or "none"
        lines.append(f"Vector {idx}: target={vector.fault}")
        lines.append(f"Inputs: {formatted}")
        lines.append(f"Detected faults ({len(detected_sorted)}): {detected_str}")
        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def _run_manual_mode(engine: AtpgEngine, circuit, collapse_result):
    """ Run PODEM in manual mode for user-selected faults. """
    faults = _collect_manual_faults(circuit, collapse_result)
    # If no faults were selected, cancel the operation
    if not faults:
        print("PODEM cancelled.")
        return None
    #  run PODEM for the selected faults
    results = engine.manual(faults)
    for test_vector in results:
        _render_test_vector(circuit, test_vector)
    # Write the test vectors to an output file
    output_path = _write_test_vectors(circuit, results)
    print(f"Wrote {len(results)} PODEM test vector(s) to {output_path}")
    return {"mode": "manual", "vectors": results, "output_path": output_path}


def _summarize_faults(faults, limit=6):
    # Summarize a list of faults for display, limiting the number shown.
    if not faults:
        return "none"
    preview = ", ".join(str(f) for f in faults[:limit])
    suffix = "..." if len(faults) > limit else ""
    return f"{preview}{suffix}"


def _detect_all_faults(engine: AtpgEngine, circuit, collapse_result):
    """ Automatically detect all collapsed faults using PODEM. """
    total = len(collapse_result.collapsed_faults)
    if total == 0:
        print("No collapsed faults were found in the circuit.")
        return {"mode": "automatic", "total": 0, "detected": 0, "undetected": []}

    print(f"Detecting all {total} collapsed faults with PODEM. This may take a few moments...")
    results = engine.automatic()
    all_faults = set(collapse_result.collapsed_faults)
    vectors_found = sum(1 for vector in results if vector.vector is not None)
    detected_faults = set()
    samples = []
    # Collect detected faults and sample vectors
    for test_vector in results:
        detected_faults.update(test_vector.detected_faults)
        if test_vector.vector is not None and len(samples) < 3:
            samples.append(test_vector)
    #  collect faults that were not detected
    undetected = sorted(
        all_faults - detected_faults, key=lambda f: (f.net, f.sink or "", f.stuck_at)
    )
    detected_total = total - len(undetected)
    #  Print summary of detection results
    print(
        f"PODEM detection summary: {detected_total}/{total} collapsed faults detected "
        f"using {vectors_found} vector(s)."
    )
    #  show a subset of sample detected vectors and undetected faults
    if samples:
        print("Sample detected vectors:")
        for test_vector in samples:
            print(f"  {test_vector.fault}: {_format_vector(test_vector.vector, circuit.primary_inputs)}")
    # Display undetected faults summary
    if undetected:
        summarized = _summarize_faults(undetected)
        print(f"Undetected collapsed faults ({len(undetected)}): {summarized}")
    # Write test vectors to output file
    output_path = _write_test_vectors(circuit, results)
    print(f"Wrote {len(results)} PODEM test vector(s) to {output_path}")
    return {
        "mode": "automatic",
        "total": total,
        "detected": detected_total,
        "undetected": undetected[:10],
        "undetected_total": len(undetected),
        "detected_faults": tuple(detected_faults),
        "vectors_found": vectors_found,
        "vectors": results,
        "output_path": output_path,
    }


def run_podem(circuit, collapse_result):
    """ Main entry point to run PODEM stage in either manual or automatic mode. s"""
    if circuit is None:
        print("Please parse a circuit before running PODEM.")
        return None
    if collapse_result is None:
        print("Please perform fault collapsing before running PODEM.")
        return None
    #  set up ATPG engine with PODEM
    engine = AtpgEngine(circuit, collapse_result, PodemEngine)
    #  Prompt user to choose manual or automatic mode
    while True:
        print("\nPODEM options:")
        print("  [1] Manual: choose specific collapsed fault(s)")
        print("  [2] Automatic: attempt to detect all collapsed faults")
        print("  [q] Cancel and return to the main menu")
        choice = input("Choose an option: ").strip().lower()
        if choice == "1":
            return _run_manual_mode(engine, circuit, collapse_result)
        if choice == "2":
            return _detect_all_faults(engine, circuit, collapse_result)
        if choice in {"q", "quit"}:
            print("PODEM cancelled.")
            return None
        print("Invalid selection. Please type '1', '2', or 'q'.")
