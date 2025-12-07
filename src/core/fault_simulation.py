from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Sequence

from .fault_collapsing import CollapseResult
from models import Circuit, Fault


class SimulationMode(Enum):
    """
    Simulation modes for fault simulation.
    SERIAL: Simulate faults one at a time.
    PARALLEL: Simulate faults using bit-parallelism.
    """
    SERIAL = "serial"
    PARALLEL = "bit-parallel"


@dataclass
class FaultSimulationReport:
    """
    Report object for fault simulation results.
    Attributes:
        mode: Simulation mode used.
        vector: Input vector applied.
        detected_faults: List of detected faults.
        undetected_faults: List of undetected faults.
        simulated_faults: All faults simulated.
        propagation_map: Mapping of faults to output propagation.
    """
    mode: SimulationMode
    vector: Dict[str, int]
    detected_faults: List[Fault]
    undetected_faults: List[Fault]
    simulated_faults: Sequence[Fault]
    propagation_map: Dict[Fault, List[str]]



class FaultSimulator:
    """
    Serial and bit-parallel single stuck-at fault simulation engine.
    Simulates faults in a circuit using two modes for efficiency.
    """

    WORD_SIZE = 64

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
        mode: SimulationMode,
        vector: Dict[str, int],
        faults: Sequence[Fault] | None = None,
    ) -> FaultSimulationReport:
        """
        Run fault simulation for the given input vector and faults.
        Args:
            mode: Simulation mode (serial or parallel).
            vector: Input vector to apply.
            faults: Optional list of faults to simulate (defaults to collapsed faults).
        Returns:
            FaultSimulationReport: Results of the simulation.
        """
        simulation_faults = list(faults) if faults is not None else self._faults
        good_values = self._evaluate_good(vector)
        if mode == SimulationMode.SERIAL:
            detected, undetected, propagation_map = self._simulate_serial(
                vector, good_values, simulation_faults
            )
        elif mode == SimulationMode.PARALLEL:
            detected, undetected, propagation_map = self._simulate_bit_parallel(
                vector, good_values, simulation_faults
            )
        else:
            raise ValueError(f"Unsupported simulation mode: {mode}")
        return FaultSimulationReport(
            mode=mode,
            vector=vector,
            detected_faults=detected,
            undetected_faults=undetected,
            simulated_faults=simulation_faults,
            propagation_map=propagation_map
        )
            simulated_faults=simulation_faults,
            propagation_map=propagation_map,
        )

    @property
    def all_faults(self) -> List[Fault]:
        return list(self._all_faults)

    @property
    def collapsed_faults(self) -> List[Fault]:
        return list(self._collapsed_faults)

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
    # Bit-parallel simulation
    # ------------------------------------------------------------------

    def _simulate_bit_parallel(
        self,
        pi_values: Dict[str, int],
        good_values: Dict[str, int],
        faults: Sequence[Fault],
    ) -> tuple[List[Fault], List[Fault], Dict[Fault, List[str]]]:
        detected: List[Fault] = []
        undetected: List[Fault] = []
        chunk: List[Fault] = []
        propagation_map: Dict[Fault, List[str]] = {}

        def flush_chunk(chunk_items: Sequence[Fault]) -> None:
            if not chunk_items:
                return
            mask, chunk_propagation = self._simulate_fault_chunk(
                chunk_items, pi_values, good_values
            )
            for bit, fault in enumerate(chunk_items):
                po_list = chunk_propagation.get(bit, [])
                propagation_map[fault] = po_list
                if mask & (1 << bit):
                    detected.append(fault)
                else:
                    undetected.append(fault)

        for fault in faults:
            if good_values.get(fault.net, 0) == fault.stuck_at:
                undetected.append(fault)
                propagation_map[fault] = []
                continue
            chunk.append(fault)
            if len(chunk) == self.WORD_SIZE:
                flush_chunk(chunk)
                chunk = []

        flush_chunk(chunk)
        return detected, undetected, propagation_map

    def _simulate_fault_chunk(
        self,
        faults: Sequence[Fault],
        pi_values: Dict[str, int],
        good_values: Dict[str, int],
    ) -> tuple[int, Dict[int, List[str]]]:
        bit_count = len(faults)
        all_mask = (1 << bit_count) - 1
        zero_masks: Dict[str, int] = {}
        one_masks: Dict[str, int] = {}
        branch_zero_masks: Dict[tuple[str, str], int] = {}
        branch_one_masks: Dict[tuple[str, str], int] = {}

        for bit, fault in enumerate(faults):
            mask = 1 << bit
            if fault.sink:
                key = (fault.net, fault.sink)
                if fault.stuck_at == 0:
                    branch_zero_masks[key] = branch_zero_masks.get(key, 0) | mask
                else:
                    branch_one_masks[key] = branch_one_masks.get(key, 0) | mask
                continue
            if fault.stuck_at == 0:
                zero_masks[fault.net] = zero_masks.get(fault.net, 0) | mask
            else:
                one_masks[fault.net] = one_masks.get(fault.net, 0) | mask

        net_values: Dict[str, int] = {}
        for pi in self.circuit.primary_inputs:
            base = all_mask if pi_values.get(pi, 0) else 0
            net_values[pi] = self._apply_fault_masks(
                base,
                zero_masks.get(pi, 0),
                one_masks.get(pi, 0),
            )

        for gate_name in self._topological_order:
            gate = self.circuit.gates[gate_name]
            inputs: List[int] = []
            for inp in gate.inputs:
                input_value = net_values[inp]
                zero_mask = branch_zero_masks.get((inp, gate.name), 0)
                one_mask = branch_one_masks.get((inp, gate.name), 0)
                if zero_mask or one_mask:
                    input_value = self._apply_fault_masks(input_value, zero_mask, one_mask)
                inputs.append(input_value)
            gate_value = self._evaluate_gate_bits(gate.type, inputs, all_mask)
            gate_value = self._apply_fault_masks(
                gate_value,
                zero_masks.get(gate.output, 0),
                one_masks.get(gate.output, 0),
            )
            net_values[gate.output] = gate_value

        detected_mask = 0
        propagation_map: Dict[int, List[str]] = {}
        for po in self.circuit.primary_outputs:
            faulty_mask = net_values.get(po, all_mask if good_values.get(po, 0) else 0)
            good_mask = all_mask if good_values.get(po, 0) else 0
            diff_mask = faulty_mask ^ good_mask
            detected_mask |= diff_mask
            bit_mask = diff_mask
            while bit_mask:
                lowest = bit_mask & -bit_mask
                bit_index = lowest.bit_length() - 1
                propagation_map.setdefault(bit_index, []).append(po)
                bit_mask &= bit_mask - 1
        return detected_mask, propagation_map

    @staticmethod
    def _apply_fault_masks(value: int, zero_mask: int, one_mask: int) -> int:
        if zero_mask:
            value &= ~zero_mask
        if one_mask:
            value |= one_mask
        return value

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _evaluate_good(self, pi_values: Dict[str, int]) -> Dict[str, int]:
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

    @staticmethod
    def _evaluate_gate_bits(
        gate_type: str,
        inputs: Sequence[int],
        all_mask: int,
    ) -> int:
        gate_type = gate_type.lower()
        if gate_type in {"and", "nand"}:
            value = inputs[0] if inputs else all_mask
            for val in inputs[1:]:
                value &= val
            if gate_type == "nand":
                value = (~value) & all_mask
            return value
        if gate_type in {"or", "nor"}:
            value = inputs[0] if inputs else 0
            for val in inputs[1:]:
                value |= val
            if gate_type == "nor":
                value = (~value) & all_mask
            return value
        if gate_type in {"not", "inv", "inverter"}:
            return (~inputs[0]) & all_mask
        if gate_type in {"buf", "buffer"}:
            return inputs[0]
        raise ValueError(f"Unsupported gate type: {gate_type}")

    def _topological_sort(self) -> List[str]:
        graph: Dict[str, List[str]] = {name: [] for name in self.circuit.gates}
        indegree: Dict[str, int] = {name: 0 for name in self.circuit.gates}

        for gate in self.circuit.gates.values():
            for inp in gate.inputs:
                source = self.circuit.nets[inp].source
                if source in graph:
                    graph[source].append(gate.name)
                    indegree[gate.name] += 1

        queue: deque[str] = deque([name for name, deg in indegree.items() if deg == 0])
        order: List[str] = []

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
