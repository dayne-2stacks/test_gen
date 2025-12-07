from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from models import Circuit, Gate, Net


class NetlistParseError(RuntimeError):
    """Raised when the netlist contains malformed statements."""


class NetlistParser:
    """Pure parsing logic for benchmark circuit netlists."""

    def parse_file(self, path: str | Path) -> Circuit:
        path = Path(path)
        lines = self._read_lines(path)
        circuit = self.parse_lines(lines)
        circuit.source = str(path)
        return circuit

    def parse_lines(self, lines: Iterable[str]) -> Circuit:
        nets: Dict[str, Net] = {}
        gates: Dict[str, Gate] = {}
        primary_inputs: List[str] = []
        primary_outputs: List[str] = []
        pi_set: set[str] = set()
        po_set: set[str] = set()

        for line_no, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("$"):
                continue

            relevant, comment = self._split_comment(raw_line)
            if not relevant and not comment:
                continue

            tokens = relevant.split()
            if not tokens:
                continue

            comment_lower = comment.lower()
            identifier = tokens[0]

            if "primary input" in comment_lower:
                net = nets.setdefault(identifier, Net(name=identifier))
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

            if "primary output" in comment_lower:
                net = nets.setdefault(identifier, Net(name=identifier))
                if identifier not in po_set:
                    primary_outputs.append(identifier)
                    po_set.add(identifier)
                net.is_primary_output = True
                continue

            if len(tokens) < 3:
                raise NetlistParseError(
                    f"Line {line_no}: expected 'output gate_type input1 [input2 ...]', "
                    f"got '{relevant}'."
                )

            output_name = tokens[0]
            gate_type = tokens[1].lower()
            input_names = tokens[2:]

            if output_name in gates:
                raise NetlistParseError(
                    f"Line {line_no}: multiple definitions for gate/net '{output_name}'."
                )

            gate = Gate(
                name=output_name,
                type=gate_type,
                inputs=input_names,
                output=output_name,
            )
            gates[output_name] = gate

            out_net = nets.setdefault(output_name, Net(name=output_name))

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

        return Circuit(
            nets=nets,
            gates=gates,
            primary_inputs=primary_inputs,
            primary_outputs=primary_outputs,
        )

    @staticmethod
    def _split_comment(line: str) -> tuple[str, str]:
        if "$" not in line:
            return line.strip(), ""
        relevant, comment = line.split("$", 1)
        return relevant.strip(), comment.strip()

    @staticmethod
    def _read_lines(path: Path) -> List[str]:
        for encoding in ("utf-8", "cp1252"):
            try:
                with path.open("r", encoding=encoding) as file:
                    return file.readlines()
            except UnicodeDecodeError:
                continue
        with path.open("r", encoding="utf-8", errors="ignore") as file:
            return file.readlines()


def parse_netlist(path: str | Path) -> Circuit:
    """Initialize a parser and parse a netlist from disk."""
    return NetlistParser().parse_file(path)


__all__ = ["NetlistParseError", "NetlistParser", "parse_netlist"]
