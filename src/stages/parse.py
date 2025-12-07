from core import log_stage_output
from core.netlist_parser import NetlistParseError, parse_netlist



def read_netlist(file_path: str):
    """
    Parse the netlist from the given file path and print summary information.
    Args:
        file_path: Path to the netlist file.
    Returns:
        Circuit object if parsing succeeds, else None.
    """
    try:
        circuit = parse_netlist(file_path)
        print(f"Successfully parsed netlist from {file_path}")
        print(f"Primary Inputs: {circuit.primary_inputs}")
        print(f"Primary Outputs: {circuit.primary_outputs}")
        print(f"Gates: {list(circuit.gates.keys())}")
        print("")
        _write_circuit_details(circuit)
        return circuit
    except NetlistParseError as e:
        print(f"Error parsing netlist: {e}")
        return None

def _write_circuit_details(circuit):
    """
    Write a summary of the parsed circuit to an output file and print details.
    Args:
        circuit: Circuit object to summarize.
    """
    source = getattr(circuit, "source", None) or "circuit"
    primary_inputs = ", ".join(circuit.primary_inputs) if circuit.primary_inputs else "-"
    primary_outputs = ", ".join(circuit.primary_outputs) if circuit.primary_outputs else "-"

    lines = [
        f"Circuit source: {source}",
        f"Primary inputs ({len(circuit.primary_inputs)}): {primary_inputs}",
        f"Primary outputs ({len(circuit.primary_outputs)}): {primary_outputs}",
        f"Gates ({len(circuit.gates)}):",
    ]

    # List all gates in the circuit
    for gate_name, gate in circuit.gates.items():
        inputs = ", ".join(gate.inputs) if gate.inputs else "-"
        lines.append(f"  {gate_name}: {gate.type}({inputs}) -> {gate.output}")

    # Uncomment below to list all nets and their drivers/sinks
    # lines.append(f"Nets ({len(circuit.nets)}):")
    # for net_name, net in circuit.nets.items():
    #     driver = net.source or ("<PI>" if net.is_primary_input else "-")
    #     sinks = ", ".join(net.sinks) if net.sinks else "-"
    #     flags = []
    #     if net.is_primary_input:
    #         flags.append("PI")
    #     if net.is_primary_output:
    #         flags.append("PO")
    #     flag_str = f" [{' '.join(flags)}]" if flags else ""
    #     lines.append(f"  {net_name}: source={driver}, sinks={sinks}{flag_str}")

    source = getattr(circuit, "source", None)
    output_source = source or "parse_results.out"
    output_file = log_stage_output(output_source, "parse", lines)
    print(f"Circuit details written to {output_file}")
