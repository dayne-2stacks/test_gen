from models import Fault
from core.podem import PodemEngine


def _prompt_fault(circuit, collapse_result):
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


def _render_test_vector(circuit, vector):
    ordered = [(pi, vector.get(pi, 0)) for pi in circuit.primary_inputs]
    rendered = ", ".join(f"{pi}={val}" for pi, val in ordered)
    print(f"  {rendered}")


def _run_single_fault_mode(circuit, collapse_result):
    fault = _prompt_fault(circuit, collapse_result)
    if fault is None:
        print("PODEM cancelled.")
        return None

    engine = PodemEngine(circuit)
    vector = engine.find_test(fault)
    if vector is None:
        print(f"No detecting vector found for {fault}.")
        return None

    print(f"Found test vector for {fault}:")
    _render_test_vector(circuit, vector)
    return {"mode": "single", "fault": fault, "vector": vector}


def _summarize_faults(faults, limit=6):
    if not faults:
        return "none"
    preview = ", ".join(str(f) for f in faults[:limit])
    suffix = "..." if len(faults) > limit else ""
    return f"{preview}{suffix}"


def _detect_all_faults(circuit, collapse_result):
    total = len(collapse_result.collapsed_faults)
    if total == 0:
        print("No collapsed faults were found in the circuit.")
        return {"mode": "bulk", "total": 0, "detected": 0, "undetected": []}

    print(f"Detecting all {total} collapsed faults with PODEM. This may take a few moments...")
    engine = PodemEngine(circuit)
    detected = 0
    undetected = []
    samples = []
    for fault in collapse_result.collapsed_faults:
        vector = engine.find_test(fault)
        if vector is None:
            undetected.append(fault)
        else:
            detected += 1
            # if len(samples) < 3:
            samples.append((fault, vector))

    print(f"PODEM detection summary: {detected} of {total} collapsed faults detected.")
    if samples:
        print("Sample detected vectors:")
        for fault, vector in samples:
            print(f"  {fault}: ", end="")
            _render_test_vector(circuit, vector)
    if undetected:
        summarized = _summarize_faults(undetected)
        print(f"Undetected collapsed faults ({len(undetected)}): {summarized}")

    return {
        "mode": "bulk",
        "total": total,
        "detected": detected,
        "undetected": undetected[:10],
        "undetected_total": len(undetected),
    }


def run_podem(circuit, collapse_result):
    if circuit is None:
        print("Please parse a circuit before running PODEM.")
        return None
    if collapse_result is None:
        print("Please perform fault collapsing before running PODEM.")
        return None

    while True:
        print("\nPODEM options:")
        print("  [1] Inject a single fault (current behavior)")
        print("  [2] Attempt to detect all collapsed faults")
        print("  [q] Cancel and return to the main menu")
        choice = input("Choose an option: ").strip().lower()
        if choice == "1":
            return _run_single_fault_mode(circuit, collapse_result)
        if choice == "2":
            return _detect_all_faults(circuit, collapse_result)
        if choice in {"q", "quit"}:
            print("PODEM cancelled.")
            return None
        print("Invalid selection. Please type '1', '2', or 'q'.")
