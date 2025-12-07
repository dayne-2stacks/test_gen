from __future__ import annotations

from typing import Dict, List, Optional

from core.boolean_sat import SatAtpg
from models import Fault


def _prompt_fault(circuit, collapse_result) -> Optional[Fault]:
    total = len(collapse_result.collapsed_faults)
    preview = ", ".join(str(f) for f in collapse_result.collapsed_faults[:8])
    if preview:
        print(f"Example collapsed faults ({min(total, 8)}/{total}): {preview}")
    while True:
        raw = input("Enter target fault as '<net> <stuck_at>' or 'q' to cancel: ").strip()
        if not raw:
            print("Please provide a net name and stuck-at value.")
            continue
        if raw.lower() in {"q", "quit"}:
            return None
        parts = raw.split()
        if len(parts) != 2 or parts[1] not in {"0", "1"}:
            print("Format must be '<net> <0|1>'.")
            continue
        net, stuck = parts[0], int(parts[1])
        if net not in circuit.nets:
            print(f"Net '{net}' not found in the circuit.")
            continue
        fault = Fault(net=net, stuck_at=stuck)
        representative = collapse_result.fault_to_representative.get(fault)
        if representative is None:
            print("Fault not present in the collapsed set; please choose another.")
            continue
        return representative


def _format_vector(vector: Dict[str, int], primary_inputs: List[str]) -> str:
    ordered = [(pi, vector.get(pi, 0)) for pi in primary_inputs]
    return ", ".join(f"{pi}={val}" for pi, val in ordered)


def _prompt_sat_mode() -> Optional[str]:
    print("""
        Boolean SAT Generation Options:
        [0] Target a single collapsed fault
        [1] Detect every collapsed fault
        [2] Cancel
        """)
    while True:
        selection = input("Select SAT mode (0-2): ").strip()
        if selection == "0":
            return "single"
        if selection == "1":
            return "all"
        if selection in {"2", "q", "quit"}:
            return None
        print("Please enter 0, 1, or 2.")


def _run_single_fault(circuit, collapse_result) -> Optional[Dict[str, object]]:
    fault = _prompt_fault(circuit, collapse_result)
    if fault is None:
        print("Boolean SAT generation cancelled.")
        return None

    engine = SatAtpg(circuit)
    vector = engine.find_test(fault)
    if vector is None:
        print(f"No detecting vector found for {fault}.")
        return None

    rendered = _format_vector(vector, circuit.primary_inputs)
    print(f"Found SAT-based test vector for {fault}:")
    print(f"  {rendered}")
    return {"mode": "single", "fault": fault, "vector": vector}


def _run_detect_all(circuit, collapse_result) -> Dict[str, object]:
    collapsed_faults = collapse_result.collapsed_faults
    total = len(collapsed_faults)
    print(f"Attempting SAT detection for all {total} collapsed faults...")

    engine = SatAtpg(circuit)
    detected = 0
    detected_examples: List[str] = []
    undetected_examples: List[str] = []

    for fault in collapsed_faults:
        vector = engine.find_test(fault)
        if vector is not None:
            detected += 1
            if len(detected_examples) < 3:
                detected_examples.append(f"{fault}: {_format_vector(vector, circuit.primary_inputs)}")
            continue
        if len(undetected_examples) < 5:
            undetected_examples.append(str(fault))

    undetected_count = total - detected
    if detected_examples:
        print("Detected examples:")
        for example in detected_examples:
            print(f"  {example}")
    print(
        f"SAT summary: detected {detected}/{total} collapsed faults; {undetected_count} remain undetected."
    )
    if undetected_examples:
        preview = ", ".join(undetected_examples)
        print(f"First undetected representatives: {preview}")

    return {
        "mode": "all",
        "total": total,
        "detected": detected,
        "undetected_count": undetected_count,
        "detected_examples": detected_examples,
        "undetected_examples": undetected_examples,
    }


def run_boolean_satisfiability(circuit, collapse_result):
    if circuit is None:
        print("Please parse a circuit before running Boolean SAT generation.")
        return None
    if collapse_result is None:
        print("Please perform fault collapsing before running Boolean SAT generation.")
        return None

    mode = _prompt_sat_mode()
    if mode is None:
        print("Boolean SAT generation cancelled.")
        return None

    if mode == "single":
        return _run_single_fault(circuit, collapse_result)
    return _run_detect_all(circuit, collapse_result)
