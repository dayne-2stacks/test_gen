from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict,  List, Optional
# TODO: add easy to understand comments for this page in a short concise manner in a human readable, non robootic way
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
    level: Optional[int] = None  # Logic level in circuit
    control: Optional[int] = None  # Used for fault modeling
    inverted: bool = False  # Used for fault modeling
    fault_list: Optional[List[Fault]] = None  # List of faults on this gate

@dataclass
class Circuit:
    """Container for all parsed circuit elements."""
    nets: Dict[str, Net]
    gates: Dict[str, Gate]
    primary_inputs: List[str]
    primary_outputs: List[str]
    source: Optional[str] = None
    fault_list: Optional[List[Fault]] = None # List of all faults in the circuit

    def net(self, name: str) -> Net:
        return self.nets[name]

    def gate(self, name: str) -> Gate:
        return self.gates[name]

@dataclass(frozen=True)
class Fault:
    """Represents a single stuck-at fault on a net."""
    net: str
    stuck_at: int  # 0 or 1

    def __str__(self) -> str:
        return f"{self.net}-SA-{self.stuck_at}"

    __repr__ = __str__
