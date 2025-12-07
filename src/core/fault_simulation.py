from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .fault_collapsing import CollapseResult
from models import Circuit, Fault


@dataclass
class FaultSimulationReport:
    """
    Report object for fault simulation results.
    """
    vector: Dict[str, int]
    detected_faults: List[Fault]
    undetected_faults: List[Fault]
    simulated_faults: Sequence[Fault]
    propagation_map: Dict[Fault, List[str]]



class FaultSimulator:
    """
    Serial single stuck-at fault simulation engine.
    """

    def __init__(self, circuit: Circuit, collapse_result: CollapseResult):
        """
        Initialize the simulator with a circuit and fault collapsing result.
        Args:
            circuit: Circuit to simulate.
            collapse_result: Result of fault collapsing.
        """
        self.circuit = circuit
        self.collapse_result = collapse_result
        self._collapsed_faults = collapse_result.collapsed_faults
        self._all_faults = self._collect_all_faults()
        self._faults = self._collapsed_faults
        self._topological_order = self._topological_sort()

    def run(
        self,
        vector: Dict[str, int],
        faults: Sequence[Fault] | None = None,
    ) -> FaultSimulationReport:
        """
        Run fault simulation for the given input vector and faults.
        Args:
            vector: Input vector to apply.
            faults: Optional list of faults to simulate (defaults to collapsed faults).
        Returns:
            FaultSimulationReport: Results of the simulation.
        """
        simulation_faults = list(faults) if faults is not None else self._faults
        good_values = self._evaluate_good(vector)
        detected, undetected, propagation_map = self._simulate_serial(
            vector, good_values, simulation_faults
        )
        return FaultSimulationReport(
            vector=vector,
            detected_faults=detected,
            undetected_faults=undetected,
            simulated_faults=simulation_faults,
            propagation_map=propagation_map
        )
    # List of all faults
    @property
    def all_faults(self) -> List[Fault]:
        return list(self._all_faults)
    # List of collapsed faults
    @property
    def collapsed_faults(self) -> List[Fault]:
        return list(self._collapsed_faults)

    # Collect all faults in the circuits
    def _collect_all_faults(self) -> List[Fault]:
        faults = list(self.collapse_result.fault_to_representative.keys())
        if not faults:
            faults = []
            for net_name, net in self.circuit.nets.items():
                for stuck_at in (0, 1):
                    faults.append(Fault(net=net_name, stuck_at=stuck_at))
                if len(net.sinks) > 1:
                    for sink in net.sinks:
                        faults.append(Fault(net=net_name, stuck_at=0, sink=sink))
                        faults.append(Fault(net=net_name, stuck_at=1, sink=sink))
        return sorted(
            faults,
            key=lambda fault: (fault.net, fault.sink or "", fault.stuck_at),
        )

    # ------------------------------------------------------------------
    # Serial simulation
    # ------------------------------------------------------------------
    def _simulate_serial(
        self,
        pi_values: Dict[str, int],
        good_values: Dict[str, int],
        faults: Sequence[Fault],
    ) -> tuple[List[Fault], List[Fault], Dict[Fault, List[str]]]:
        detected: List[Fault] = []
        undetected: List[Fault] = []
        good_outputs = {po: good_values.get(po, 0) for po in self.circuit.primary_outputs}

        propagation_map: Dict[Fault, List[str]] = {}
        for fault in faults:
            if good_values.get(fault.net, 0) == fault.stuck_at:
                propagation_map[fault] = []
                undetected.append(fault)
                continue
            faulty_outputs = self._evaluate_faulty_outputs(pi_values, fault)
            differences = [
                po
                for po in self.circuit.primary_outputs
                if faulty_outputs.get(po, 0) != good_outputs.get(po, 0)
            ]
            propagation_map[fault] = differences
            if differences:
                detected.append(fault)
            else:
                undetected.append(fault)

        return detected, undetected, propagation_map

    def _evaluate_faulty_outputs(
        self,
        pi_values: Dict[str, int],
        fault: Fault,
    ) -> Dict[str, int]:
        values: Dict[str, int] = {}

        for pi in self.circuit.primary_inputs:
            value = pi_values.get(pi, 0)
            if fault.sink is None and pi == fault.net:
                value = fault.stuck_at
            values[pi] = value

        for gate_name in self._topological_order:
            gate = self.circuit.gates[gate_name]
            inputs = []
            for inp in gate.inputs:
                inp_value = values[inp]
                if fault.net == inp and fault.sink == gate.name:
                    inp_value = fault.stuck_at
                inputs.append(inp_value)
            gate_value = self._evaluate_gate_scalar(gate.type, inputs)
            if fault.sink is None and gate.output == fault.net:
                gate_value = fault.stuck_at
            values[gate.output] = gate_value

        return {po: values.get(po, 0) for po in self.circuit.primary_outputs}

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _evaluate_good(self, pi_values: Dict[str, int]) -> Dict[str, int]:
        """Evaluate the circuit outputs for given primary input values without any faults."""
        values: Dict[str, int] = {}
        for pi in self.circuit.primary_inputs:
            values[pi] = pi_values.get(pi, 0)

        for gate_name in self._topological_order:
            gate = self.circuit.gates[gate_name]
            inputs = [values[inp] for inp in gate.inputs]
            values[gate.output] = self._evaluate_gate_scalar(gate.type, inputs)
        return values

    @staticmethod
    def _evaluate_gate_scalar(gate_type: str, inputs: Sequence[int]) -> int:
        """ Evaluate a gate's output value given its type and input values. """
        gate_type = gate_type.lower()
        if gate_type in {"and", "nand"}:
            value = 1
            for val in inputs:
                value &= 1 if val else 0
            if gate_type == "nand":
                value = 0 if value else 1
            return value
        if gate_type in {"or", "nor"}:
            value = 0
            for val in inputs:
                value |= 1 if val else 0
            if gate_type == "nor":
                value = 0 if value else 1
            return value
        if gate_type in {"not", "inv", "inverter"}:
            return 0 if inputs[0] else 1
        if gate_type in {"buf", "buffer"}:
            return inputs[0]
        raise ValueError(f"Unsupported gate type: {gate_type}")

    def _topological_sort(self) -> List[str]:
        """ Sort gates in topological order for simulation. """
        graph: Dict[str, List[str]] = {name: [] for name in self.circuit.gates}
        indegree: Dict[str, int] = {name: 0 for name in self.circuit.gates}
        # Build the graph and indegree counts
        for gate in self.circuit.gates.values():
            for inp in gate.inputs:
                source = self.circuit.nets[inp].source
                if source in graph:
                    graph[source].append(gate.name)
                    indegree[gate.name] += 1

        queue: deque[str] = deque([name for name, deg in indegree.items() if deg == 0])
        order: List[str] = []
        # Perform topological sort
        while queue:
            gate_name = queue.popleft()
            order.append(gate_name)
            for neighbor in graph.get(gate_name, []):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.circuit.gates):
            raise ValueError("Circuit contains cycles; unable to simulate.")
        return order
