"""
Netlist parser for the Automatic Test Generation (ATG) project.

The parser represents the .ckt files as a collection of nets and gates with primary input and output annotations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional

from models import Circuit, Gate, Net
import argparse


class NetlistParseError(RuntimeError):
    """Raised when the netlist contains malformed statements."""


class NetlistParser:
    """Netlist Parser for the benchmark circuit netlists."""
    
    def parse_file(self, path: str | Path) -> Circuit:
        """Parse a netlist stored on disk."""
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as file:
                lines = file.readlines()
        except UnicodeDecodeError:
            with path.open("r", encoding="cp1252") as file:
                lines = file.readlines()
        circuit = self._parse_lines(lines)
        circuit.source = str(path)
        return circuit

    def parse(self, text: str, *, source: Optional[str] = None) -> Circuit:
        """Parse a provided netlist"""
        circuit = self._parse_lines(text.splitlines())
        circuit.source = source
        return circuit

    def _parse_lines(self, lines: Iterable[str]) -> Circuit:
        nets: Dict[str, Net] = {}
        gates: Dict[str, Gate] = {}
        primary_inputs: List[str] = []
        primary_outputs: List[str] = []
        pi_set: set[str] = set()
        po_set: set[str] = set()

        for line_no, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            
            # Skip line if empty or comment only
            if not stripped:
                continue
            if stripped.startswith("$"):
                continue
            
            # Parses gate/net definition and comments about gate/net
            relevant, comment = self._split_comment(raw_line)
            
            # If the line is just a comment character, skip
            if not relevant and not comment:
                continue
            
            # Split gate/net definition by word
            tokens = relevant.split()
            
            # If no words (nets or gate) are present, skip
            if not tokens:
                continue
            
            # make comment lowercase for consistent parsing
            comment_lower = comment.lower()
            # select the gate/net (First item in the line)
            identifier = tokens[0]

            # Case 1: Net is a primary input
            # if the comment indicates primary input, add as a primary input net
            if "primary input" in comment_lower:
                # Create a net with its identifier as name
                net = nets.setdefault(identifier, Net(name=identifier))
                # Primary inputs cannot be driven by 2 sources
                if net.source is not None and not net.is_primary_input:
                    raise NetlistParseError(
                        f"Line {line_no}: primary input '{identifier}' is already driven "
                        f"by gate '{net.source}'."
                    )
                if identifier not in pi_set:
                    primary_inputs.append(identifier)
                    pi_set.add(identifier)
                net.is_primary_input = True
                net.source = None
                continue
            
            # Case 2: Net is a primary output
            # Handle primary output annotation
            if "primary output" in comment_lower:
                net = nets.setdefault(identifier, Net(name=identifier))
                if identifier not in po_set:
                    primary_outputs.append(identifier)
                    po_set.add(identifier)
                net.is_primary_output = True
                continue
            
            # Case 3: Gate definition
            if len(tokens) < 3:
                raise NetlistParseError(
                    f"Line {line_no}: expected 'output gate_type input1 [input2 ...]', "
                    f"got '{relevant}'."
                )

            output_name = tokens[0] # Output net
            gate_type = tokens[1].lower() # type of gate
            input_names = tokens[2:] # inputs (all remaining tokens in line)

            if output_name in gates:
                raise NetlistParseError(
                    f"Line {line_no}: multiple definitions for gate/net '{output_name}'."
                )
                
            # create gate
            gate = Gate(
                name=output_name,
                type=gate_type,
                inputs=input_names,
                output=output_name,
            )
            gates[output_name] = gate
            
            out_net = nets.setdefault(output_name, Net(name=output_name))
            
            # Internal node cannot be a primary input
            if out_net.is_primary_input:
                raise NetlistParseError(
                    f"Line {line_no}: primary input '{output_name}' driven by gate."
                )
            if out_net.source and out_net.source != output_name:
                raise NetlistParseError(
                    f"Line {line_no}: net '{output_name}' already driven by '{out_net.source}'."
                )
            out_net.source = output_name

            for input_name in input_names:
                net = nets.setdefault(input_name, Net(name=input_name))
                net.add_sink(output_name)

        # Create circuit after all, nets, PIs and POs have been processed
        return Circuit(
            nets=nets,
            gates=gates,
            primary_inputs=primary_inputs,
            primary_outputs=primary_outputs,
        )

    @staticmethod
    def _split_comment(line: str) -> tuple[str, str]:
        """Split a line into gate info and comment."""
        if "$" not in line:
            return line.strip(), ""
        relevant, comment = line.split("$", 1)
        return relevant.strip(), comment.strip()


def parse_netlist(path: str | Path) -> Circuit:
    """Initialize a parser and parse a netlist from disk."""
    return NetlistParser().parse_file(path)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Parse a netlist file.")
    parser.add_argument("path", type=str, help="Path to the netlist file to parse.")
    args = parser.parse_args()

    try:
        circuit = parse_netlist(args.path)
        print(f"Successfully parsed netlist from {args.path}")
        print(f"Primary Inputs: {circuit.primary_inputs}")
        print(f"Primary Outputs: {circuit.primary_outputs}")
        print(f"Gates: {list(circuit.gates.keys())}")
    except NetlistParseError as e:
        print(f"Error parsing netlist: {e}")
