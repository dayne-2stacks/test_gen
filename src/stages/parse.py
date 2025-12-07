from core import log_stage_output
from core.netlist_parser import NetlistParseError, parse_netlist



def read_netlist(file_path: str):
    """
    Parse the netlist from the given file path and print summary information.
    """
    try:
        # use parser to parse netlist and print details
        circuit = parse_netlist(file_path)
        print(f"Successfully parsed netlist from {file_path}")
        print(f"Primary Inputs: {circuit.primary_inputs}")
        print(f"Primary Outputs: {circuit.primary_outputs}")
        print(f"Gates: {list(circuit.gates.keys())}")
        print("")
        # write outputs to file
        _write_circuit_details(circuit)
        return circuit
    # handle error if any
    except NetlistParseError as e:
        print(f"Error parsing netlist: {e}")
        return None

def _write_circuit_details(circuit):
    """
    Write a summary of the parsed circuit to an output file and print details.
    """
    # gather circuit details foor logging to file
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


    source = getattr(circuit, "source", None)
    output_source = source or "parse_results.out"
    output_file = log_stage_output(output_source, "parse", lines)
    print(f"Circuit details written to {output_file}")
