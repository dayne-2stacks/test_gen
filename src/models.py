from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict,  List, Optional
from enum import Enum

# Core data structures the rest of the tool uses to describe a circuit and its faults.
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
        # Keep track of the sink list of each net
        if gate_name not in self.sinks:
            self.sinks.append(gate_name)            

@dataclass
class Gate:
    """A logic gate defined in the netlist."""
    name: str
    type: str
    inputs: List[str]
    output: str
    level: Optional[int] = None  # depth of gate
    control: Optional[int] = None  # controlling value used during simulation.
    inverted: bool = False  # Marks gates that flip logic level for fault reasoning.
    fault_list: Optional[List[Fault]] = None  # Faults affecting this gate's behavior.

@dataclass
class Circuit:
    """Container for all parsed circuit elements."""
    nets: Dict[str, Net]
    gates: Dict[str, Gate]
    primary_inputs: List[str]
    primary_outputs: List[str]
    source: Optional[str] = None
    fault_list: Optional[List[Fault]] = None  # All faults defined anywhere in the circuit.

    def net(self, name: str) -> Net:
        # helper to fetch a net by name.
        return self.nets[name]

    def gate(self, name: str) -> Gate:
        # helper to fetch a gate by name.
        return self.gates[name]

@dataclass(frozen=True)
class Fault:
    """Represents a single stuck-at fault on a net."""
    net: str
    stuck_at: int  # 0 or 1
    sink: Optional[str] = None  # Specific fanout branch; None means the net/stem

    def __str__(self) -> str:
        location = f"{self.net}->{self.sink}" if self.sink else self.net
        return f"{location}-SA-{self.stuck_at}"

    __repr__ = __str__
    
    
class SignalValue(Enum):
    ZERO = 0
    ONE = 1
    X = 2
    D = 3
    D_BAR = 4

    def invert(self) -> "SignalValue":
        return {
            SignalValue.ZERO: SignalValue.ONE,
            SignalValue.ONE: SignalValue.ZERO,
            SignalValue.X: SignalValue.X,
            SignalValue.D: SignalValue.D_BAR,
            SignalValue.D_BAR: SignalValue.D,
        }[self]

    def is_faulty(self) -> bool:
        return self in {SignalValue.D, SignalValue.D_BAR}


def signal_and(a: SignalValue, b: SignalValue) -> SignalValue:
    if a == SignalValue.ZERO or b == SignalValue.ZERO:
        return SignalValue.ZERO
    if a == SignalValue.ONE:
        return b
    if b == SignalValue.ONE:
        return a
    if a == b:
        return a
    if {a, b} == {SignalValue.D, SignalValue.D_BAR}:
        return SignalValue.ZERO
    return SignalValue.X


def signal_or(a: SignalValue, b: SignalValue) -> SignalValue:
    if a == SignalValue.ONE or b == SignalValue.ONE:
        return SignalValue.ONE
    if a == SignalValue.ZERO:
        return b
    if b == SignalValue.ZERO:
        return a
    if a == b:
        return a
    if {a, b} == {SignalValue.D, SignalValue.D_BAR}:
        return SignalValue.ONE
    return SignalValue.X
