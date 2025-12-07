
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict,  List, Optional
from enum import Enum

# Core data structures for representing a digital circuit and its faults.

@dataclass
class Net:
    """
    Represents a signal net in the circuit.
    """
    name: str
    source: Optional[str] = None
    sinks: List[str] = field(default_factory=list)
    is_primary_input: bool = False
    is_primary_output: bool = False

    def add_sink(self, gate_name: str) -> None:
        """
        Register that `gate_name` reads this net.
        """
        if gate_name not in self.sinks:
            self.sinks.append(gate_name)

@dataclass
class Gate:
    """
    Represents a logic gate in the netlist.
    """
    name: str
    type: str
    inputs: List[str]
    output: str
    level: Optional[int] = None
    control: Optional[int] = None
    inverted: bool = False
    fault_list: Optional[List['Fault']] = None

@dataclass
class Circuit:
    """
    Container for all parsed circuit elements.
    """
    nets: Dict[str, Net]
    gates: Dict[str, Gate]
    primary_inputs: List[str]
    primary_outputs: List[str]
    source: Optional[str] = None
    fault_list: Optional[List['Fault']] = None

    def net(self, name: str) -> Net:
        """
        Helper to fetch a net by name.
        """
        return self.nets[name]

    def gate(self, name: str) -> Gate:
        """
        Helper to fetch a gate by name.
        """
        return self.gates[name]

@dataclass(frozen=True)
class Fault:
    """
    Represents a single stuck-at fault on a net.
    """
    net: str
    stuck_at: int
    sink: Optional[str] = None

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
