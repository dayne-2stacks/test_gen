from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict,  List, Optional

@dataclass
class Net:
    """A signal in the circuit."""

    name: str
    source: Optional[str] = None  # Which gate drives this net, none if primary input
    sinks: List[str] = field(default_factory=list)  # gates that use this net
    is_primary_input: bool = False
    is_primary_output: bool = False

    def add_sink(self, gate_name: str) -> None:
        """Register that `gate_name` reads this net."""
        if gate_name not in self.sinks:
            self.sinks.append(gate_name)            

@dataclass
class Gate:
    """A logic gate defined in the netlist."""
    name: str
    type: str
    inputs: List[str]
    output: str

@dataclass
class Circuit:
    """Container for all parsed circuit elements."""
    nets: Dict[str, Net]
    gates: Dict[str, Gate]
    primary_inputs: List[str]
    primary_outputs: List[str]
    source: Optional[str] = None

    def net(self, name: str) -> Net:
        return self.nets[name]

    def gate(self, name: str) -> Gate:
        return self.gates[name]