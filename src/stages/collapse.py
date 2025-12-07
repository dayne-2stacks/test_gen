from core import log_stage_output
from core.fault_collapsing import FaultCollapser, prepare_fault_collapsing_output
from stages.parse import read_netlist
from pathlib import Path

def perform_fault_collapsing(circuit, file_path):
    """
    Perform fault collapsing on the given circuit.
    """
    if circuit is None:
        print("Reading the input net-list...")
        circuit = read_netlist(file_path)
        if circuit is None:
            print("Unable to perform fault collapsing without a valid circuit.")
            return None, None

    print("Performing fault collapsing...")
    collapser = FaultCollapser(circuit)
    collapse_result = collapser.collapse()
    report, total_fault_lines, summary_lines = prepare_fault_collapsing_output(
        collapse_result
    )
    collapsed_count = report.collapsed_count
    dominated_count = report.dominated_count
    print(f"Total faults: {report.total_faults}")
    print(f"Collapsed fault classes: {collapsed_count}")
    print(f"Dominated fault classes removed: {dominated_count}")

    equivalence_lines = report.equivalence_lines()
    dominance_lines = report.dominance_lines()

    # Print equivalence and dominance information
    if equivalence_lines:
        print("Equivalent fault classes:")
        for line in equivalence_lines:
            print(f"  {line}")
    if dominance_lines:
        print("Dominating faults:")
        for line in dominance_lines:
            print(f"  {line}")

    # Write results to output files
    source = getattr(circuit, "source", None) or file_path
    if source:
        root_dir = Path(__file__).resolve().parents[2]
        circuit_dir = root_dir / "outputs" / Path(source).name
        circuit_dir.mkdir(parents=True, exist_ok=True)
        total_faults_path = circuit_dir / "total_faults.out"
        total_faults_path.write_text(
            "\n".join(total_fault_lines) + "\n", encoding="utf-8"
        )
        print(f"Total faults written to {total_faults_path}")
        collapsed_faults_path = circuit_dir / "collapsed_faults.out"
        collapsed_lines = report.equivalence_lines()
        collapsed_faults_path.write_text("\n".join(collapsed_lines) + "\n", encoding="utf-8")
        print(f"Collapsed faults written to {collapsed_faults_path}")
        summary_path = log_stage_output(source, "collapse", summary_lines)
        print(f"Collapse summary written to {summary_path}")
    return circuit, collapse_result
