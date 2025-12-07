from core.fault_simulation import FaultSimulator, SimulationMode
from models import Fault
from pathlib import Path
from typing import Dict, List, Optional, Set

def _print_primary_output_values(circuit, simulator: FaultSimulator, vector: Dict[str, int]) -> None:
    if circuit is None or not getattr(circuit, "primary_outputs", None):
        return
    if not vector:
        return

    good_values = simulator._evaluate_good(vector)  # type: ignore[attr-defined]
    outputs = {po: good_values.get(po, 0) for po in circuit.primary_outputs}

    print("Primary outputs for this test vector:")
    for po in circuit.primary_outputs:
        val = outputs.get(po, 0)
        print(f"  {po}: expected={val}, observed={val}")

def _write_simulation_results_to_file(circuit, report, simulator: FaultSimulator) -> None:
    source = getattr(circuit, "source", None)
    if source:
        input_path = Path(source)
        root_dir = Path(__file__).resolve().parents[2]
        output_dir = root_dir / "outputs" / input_path.name / "simulation"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{input_path.name}.sim.out"
    else:
        output_path = Path("simulation_results.out")

    mode_label = "Serial" if report.mode == SimulationMode.SERIAL else "Bit-parallel"
    vector_summary = (
        ", ".join(f"{pi}={val}" for pi, val in report.vector.items())
        if report.vector
        else "<empty>"
    )

    po_values: Dict[str, int] = {}
    observed_po_values: Dict[Fault, Dict[str, int]] = {}
    if getattr(circuit, "primary_outputs", None) and report.vector:
        good_values = simulator._evaluate_good(report.vector)  # type: ignore[attr-defined]
        po_values = {po: good_values.get(po, 0) for po in circuit.primary_outputs}
        for fault in report.simulated_faults:
            propagated = report.propagation_map.get(fault)
            if propagated:
                observed = simulator._evaluate_faulty_outputs(report.vector, fault)  # type: ignore[attr-defined]
            else:
                observed = po_values
            observed_po_values[fault] = observed

    def _format_outputs(values: Dict[str, int]) -> str:
        return ", ".join(f"{po}={values.get(po, 0)}" for po in circuit.primary_outputs)
    expected_formatted = _format_outputs(po_values) if po_values else ""

    lines: List[str] = []
    lines.append(f"Simulation mode: {mode_label}")
    lines.append(f"Input vector: {vector_summary}")
    lines.append(f"Simulated fault classes: {len(report.simulated_faults)}")
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

    if po_values:
        lines.append("Primary outputs (expected vs observed):")
        for po in circuit.primary_outputs:
            val = po_values.get(po, 0)
            lines.append(f"  {po}: expected={val}, observed={val}")
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

def prompt_simulation_mode():
    print("""
        Fault Simulation Options:
        [0] Serial fault simulation
        [1] Bit-parallel fault simulation
        [2] Return to main menu
        """)
    selection = input("Select simulation mode (0-2): ").strip()
    if selection == "0":
        return SimulationMode.SERIAL
    if selection == "1":
        return SimulationMode.PARALLEL
    return None


def prompt_simulation_scope():
    print("""
        Fault Scope:
        [0] Simulate all single stuck-at faults
        [1] Manually select single stuck-at faults
        [2] Cancel
        """)
    selection = input("Choose simulation scope (0-2): ").strip()
    if selection == "0":
        return "auto"
    if selection == "1":
        return "manual"
    return None


def prompt_input_vector(primary_inputs):
    if not primary_inputs:
        print("Circuit does not have primary inputs; using empty vector.")
        return {}

    prompt = ", ".join(primary_inputs)
    while True:
        print(f"There are {len(primary_inputs)} primary inputs. Please insert a {len(primary_inputs)}-bit vector.")
        raw = input(
            f"Enter binary values for [{prompt}] (e.g., 0101) or 'q' to cancel: "
        ).strip()
        cleaned = "".join(raw.split())
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
    mode_label = "Serial" if report.mode == SimulationMode.SERIAL else "Bit-parallel"
    vector_summary = (
        ", ".join(f"{pi}={val}" for pi, val in report.vector.items())
        if report.vector
        else "<empty>"
    )
    print(f"{mode_label} simulation complete using vector: {vector_summary}")
    total_faults = len(report.simulated_faults)
    print(
        f"Detected {len(report.detected_faults)} of {total_faults} simulated fault classes."
    )

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
        if missing:
            if allow_both and len(unique_canonical) == 2:
                print(f"One or both faults for '{net}' are not available in the {label} set.")
            else:
                print(f"{unique_canonical[0]} is not available in the {label} set.")
            continue

        for canonical in unique_canonical:
            if canonical in seen:
                print(f"{canonical} was already added.")
                continue
            seen.add(canonical)
            selected.append(canonical)
    return selected


def run_fault_simulation(circuit, collapse_result):
    fault_scope = prompt_simulation_scope()
    if fault_scope is None:
        print("Simulation cancelled.")
        return None

    simulator = FaultSimulator(circuit, collapse_result)

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

    mode = prompt_simulation_mode()
    if mode is None:
        print("Simulation cancelled.")
        return None

    vector = prompt_input_vector(circuit.primary_inputs)
    if vector is None:
        print("Simulation cancelled.")
        return None

    report = simulator.run(mode, vector, faults=fault_targets)
    _print_primary_output_values(circuit, simulator, vector)
    display_simulation_summary(report)
    _write_simulation_results_to_file(circuit, report, simulator)
    return report
# TODO: Allow the user to choose between a single ssf each or multiple ssfs meaning both stuck at faults are present