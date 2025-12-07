from core.fault_simulation import FaultSimulationReport, FaultSimulator
from models import Fault
from pathlib import Path
from typing import Dict, List, Optional, Set


def _print_primary_output_values(
    circuit,
    simulator: FaultSimulator,
    vector: Dict[str, int],
    observed_outputs: Optional[Dict[str, int]] = None,
) -> None:
    """
    Print the expected and observed values for all primary outputs for a given test vector.
    """
    if circuit is None or not getattr(circuit, "primary_outputs", None):
        return
    if not vector:
        return

    good_values = simulator._evaluate_good(vector)
    expected_outputs = {po: good_values.get(po, 0) for po in circuit.primary_outputs}
    outputs = observed_outputs or expected_outputs
    #  Display primary output values
    print("Primary outputs for this test vector:")
    for po in circuit.primary_outputs:
        expected = expected_outputs.get(po, 0)
        observed = outputs.get(po, expected)
        print(f"  {po}: expected={expected}, observed={observed}")


def _write_simulation_results_to_file(circuit, report, simulator: FaultSimulator) -> None:
    """
    Write simulation results to an output file and print summary information.
    """
    # Determine output file path
    source = getattr(circuit, "source", None)
    if source:
        input_path = Path(source)
        root_dir = Path(__file__).resolve().parents[2]
        output_dir = root_dir / "outputs" / input_path.name / "simulation"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{input_path.name}.sim.out"
    else:
        output_path = Path("simulation_results.out")
    #  run serial simulation report writing
    mode_label = "Serial"
    vector_summary = (
        ", ".join(f"{pi}={val}" for pi, val in report.vector.items())
        if report.vector
        else "<empty>"
    )

    po_values: Dict[str, int] = {}
    observed_po_values: Dict[Fault, Dict[str, int]] = {}
    combined_outputs = getattr(report, "combined_outputs", None)
    #  Prepare primary output values for each simulated fault
    if getattr(circuit, "primary_outputs", None) and report.vector:
        good_values = simulator._evaluate_good(report.vector)  # type: ignore[attr-defined]
        po_values = {po: good_values.get(po, 0) for po in circuit.primary_outputs}
        # For each simulated fault, determine observed outputs
        for fault in report.simulated_faults:
            propagated = report.propagation_map.get(fault)
            if combined_outputs is not None:
                observed = {po: combined_outputs.get(po, 0) for po in circuit.primary_outputs}
            elif propagated:
                observed = simulator._evaluate_faulty_outputs(report.vector, fault)  # type: ignore[attr-defined]
            else:
                observed = po_values
            observed_po_values[fault] = observed

    def _format_outputs(values: Dict[str, int]) -> str:
        """Format primary output values for display."""
        return ", ".join(f"{po}={values.get(po, 0)}" for po in circuit.primary_outputs)
    expected_formatted = _format_outputs(po_values) if po_values else ""

    lines: List[str] = []
    lines.append(f"Simulation mode: {mode_label}")
    lines.append(f"Input vector: {vector_summary}")
    lines.append(f"Simulated fault classes: {len(report.simulated_faults)}")
    # Detail each simulated fault class
    if report.simulated_faults:
        lines.append("Fault class details:")
        for fault in report.simulated_faults:
            if po_values:
                observed = observed_po_values.get(fault, po_values)
                observed_formatted = (
                    expected_formatted if observed is po_values else _format_outputs(observed)
                )
                lines.append(
                    f"  {fault}: expected={expected_formatted}; observed={observed_formatted}"
                )
            else:
                lines.append(f"  {fault}")
    lines.append(f"Detected faults: {len(report.detected_faults)}")
    lines.append(f"Undetected faults: {len(report.undetected_faults)}")
    lines.append("")
    # Detail detected and undetected faults
    if po_values:
        observed_summary: Dict[str, int] = {}
        if combined_outputs is not None:
            observed_summary = {
                po: combined_outputs.get(po, 0) for po in circuit.primary_outputs
            }
        elif report.simulated_faults:
            first_fault = report.simulated_faults[0]
            observed_summary = observed_po_values.get(first_fault, po_values)
        else:
            observed_summary = po_values

        lines.append("Primary outputs (expected vs observed):")
        for po in circuit.primary_outputs:
            expected = po_values.get(po, 0)
            observed = observed_summary.get(po, expected)
            lines.append(f"  {po}: expected={expected}, observed={observed}")
        lines.append("")

    lines.append("Detected faults (with propagating outputs):")
    for fault in report.detected_faults:
        outputs = report.propagation_map.get(fault) or []
        outputs_str = ", ".join(outputs) if outputs else "-"
        lines.append(f"  {fault}: {outputs_str}")

    lines.append("")
    lines.append("Undetected faults:")
    for fault in report.undetected_faults:
        lines.append(f"  {fault}")

    if po_values and getattr(circuit, "primary_inputs", None):
        input_values = ", ".join(
            f"{pi}={report.vector.get(pi, 0)}" for pi in circuit.primary_inputs
        )
        lines.append("")
        lines.append("Simulation table (case | primary inputs | primary outputs):")
        lines.append("Case | Primary inputs | Primary outputs")
        lines.append("-" * len("Case | Primary inputs | Primary outputs"))
        lines.append(f"Good circuit | {input_values} | {expected_formatted}")
        for fault in report.simulated_faults:
            observed = observed_po_values.get(fault, po_values)
            outputs_str = _format_outputs(observed)
            lines.append(f"{fault} | {input_values} | {outputs_str}")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Simulation results written to {output_path}")

def prompt_simulation_scope():
    """ Prompt user to select fault simulation scope. """
    print("""
        Fault Scope:
        [0] Simulate all single stuck-at faults
        [1] Manually select single stuck-at faults
        [2] Cancel
        """)
    # If auto selected, return all faults; if manual, prompt for faults; if cancel, return None
    selection = input("Choose simulation scope (0-2): ").strip()
    if selection == "0":
        return "auto"
    if selection == "1":
        return "manual"
    return None


def prompt_input_vector(primary_inputs):
    """ Prompt user to enter a primary input vector. """
    if not primary_inputs:
        print("Circuit does not have primary inputs; using empty vector.")
        return {}

    prompt = ", ".join(primary_inputs)
    # Prompt user until valid input is received
    while True:
        print(f"There are {len(primary_inputs)} primary inputs. Please insert a {len(primary_inputs)}-bit vector.")
        raw = input(
            f"Enter binary values for [{prompt}] (e.g., 0101) or 'q' to cancel: "
        ).strip()
        cleaned = "".join(raw.split())
        # handle input cases
        if not cleaned:
            print("Input vector cannot be empty.")
            continue
        if cleaned.lower() in {"q", "quit"}:
            return None
        if len(cleaned) != len(primary_inputs) or any(c not in "01" for c in cleaned):
            print(f"Please provide exactly {len(primary_inputs)} binary digits.")
            continue
        return {name: int(bit) for name, bit in zip(primary_inputs, cleaned)}


def display_simulation_summary(report):
    """ Display a summary of the fault simulation results. """
    vector_summary = (
        ", ".join(f"{pi}={val}" for pi, val in report.vector.items())
        if report.vector
        else "<empty>"
    )
    print(f"Serial simulation complete using vector: {vector_summary}")
    total_faults = len(report.simulated_faults)
    print(
        f"Detected {len(report.detected_faults)} of {total_faults} simulated fault classes."
    )
    # Provide previews of detected and undetected faults
    def preview(label, faults):
        if not faults:
            return
        limit = 10
        rendered = ", ".join(str(fault) for fault in faults[:limit])
        if len(faults) > limit:
            rendered += ", ..."
        print(f"{label}: {rendered}")

    preview("Detected faults", report.detected_faults)
    preview("Undetected faults", report.undetected_faults)

    propagated = [
        (fault, outputs)
        for fault, outputs in report.propagation_map.items()
        if outputs
    ]
    if propagated:
        limit = 6
        rendered = ", ".join(
            f"{fault}->{', '.join(outputs)}"
            for fault, outputs in propagated[:limit]
        )
        if len(propagated) > limit:
            rendered += ", ..."
        print(f"Faults that reached a primary output: {rendered}")
    else:
        print("No simulated faults propagated to a primary output.")


def prompt_fault_list(
    circuit,
    available_faults,
    label,
    representative_map: Optional[Dict[Fault, Fault]] = None,
    dominance_map: Optional[Dict[Fault, Fault]] = None,
    allow_both: bool = False,
):
    """ Prompt user to select faults from a given list. """
    total = len(available_faults)
    if total:
        preview = ", ".join(str(fault) for fault in available_faults[:min(6, total)])
        print(f"Sample {label} ({min(6, total)}/{total}): {preview}")
    else:
        print(f"No {label} were found; simulating only the good circuit.")
        return []

    available_set = set(available_faults)
    selected: List[Fault] = []
    seen: Set[Fault] = set()
    # Prompt user until they finish adding faultts or cancel
    while True:
        hint = "<net> <stuck_at|both>" if allow_both else "<net> <stuck_at>"
        raw = input(
            f"Enter a fault as '{hint}' (blank to finish or 'q' to cancel): "
        ).strip()
        if not raw:
            break
        if raw.lower() in {"q", "quit"}:
            return None
        parts = raw.split()
        if len(parts) != 2:
            print(f"Please provide a net name followed by a stuck-at value (e.g., N3 0).")
            continue
        net = parts[0]
        stuck_token = parts[1].lower()
        if net not in circuit.nets:
            print(f"Net '{net}' is unknown.")
            continue
        if allow_both and stuck_token == "both":
            requested_faults = [Fault(net=net, stuck_at=0), Fault(net=net, stuck_at=1)]
        elif stuck_token in {"0", "1"}:
            requested_faults = [Fault(net=net, stuck_at=int(stuck_token))]
        else:
            print("Please provide a net name followed by 0, 1, or 'both' (e.g., N3 both).")
            continue
        # Map requested faults to their representatives
        canonical_faults: List[Fault] = []
        for fault in requested_faults:
            canonical = representative_map.get(fault, fault) if representative_map else fault
            if dominance_map:
                visited: Set[Fault] = set()
                while canonical in dominance_map and canonical not in visited:
                    visited.add(canonical)
                    canonical = dominance_map[canonical]
            canonical_faults.append(canonical)

        unique_canonical = []
        for fault in canonical_faults:
            if fault not in unique_canonical:
                unique_canonical.append(fault)

        missing = [fault for fault in unique_canonical if fault not in available_set]
        # Check for missing faults
        if missing:
            if allow_both and len(unique_canonical) == 2:
                print(f"One or both faults for '{net}' are not available in the {label} set.")
            else:
                print(f"{unique_canonical[0]} is not available in the {label} set.")
            continue
        # Add selected faults, avoiding duplicates
        for canonical in unique_canonical:
            if canonical in seen:
                print(f"{canonical} was already added.")
                continue
            seen.add(canonical)
            selected.append(canonical)
    return selected


def run_fault_simulation(circuit, collapse_result):
    """ Run fault simulation on the given circuit with user-specified options. """
    fault_scope = prompt_simulation_scope()
    if fault_scope is None:
        print("Simulation cancelled.")
        return None
    # Set up fault simulator
    simulator = FaultSimulator(circuit, collapse_result)
    # Determine fault targets based on user selection
    if fault_scope == "auto":
        fault_targets = simulator.all_faults
    else:
        selected_faults = prompt_fault_list(
            circuit,
            simulator.all_faults,
            "single stuck-at faults",
            allow_both=True,
        )
        if selected_faults is None:
            print("Simulation cancelled.")
            return None
        fault_targets = selected_faults or []
    # Prompt user for input vector
    vector = prompt_input_vector(circuit.primary_inputs)
    if vector is None:
        print("Simulation cancelled.")
        return None
    # Generate and report output
    report = simulator.run(vector, faults=fault_targets)
    observed_outputs = None
    _print_primary_output_values(circuit, simulator, vector, observed_outputs)
    display_simulation_summary(report)
    _write_simulation_results_to_file(circuit, report, simulator)
    return report
