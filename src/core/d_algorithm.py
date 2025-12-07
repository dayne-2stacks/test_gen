from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Dict, List, Optional

from models import Circuit, Fault
from models import SignalValue, signal_and, signal_or


class DAlgorithmEngine:
    """
    Source-level D-Algorithm engine ported from the reference implementation.
    Implements the D-Algorithm for automatic test pattern generation (ATPG).
    """

    def __init__(self, circuit: Circuit):
        """
        Initialize the D-Algorithm engine with a circuit.
        Args:
            circuit: Circuit object to operate on.
        """
        self.circuit = circuit
        self._topo_order = self._compute_topological_order()
        self._fault: Optional[Fault] = None

    def find_test(self, fault: Fault, *, max_depth: int = 500) -> Optional[Dict[str, int]]:
        """
        Attempt to find a test vector that detects the given fault.
        Args:
            fault: Fault to target.
            max_depth: Maximum recursion depth.
        Returns:
            Optional[Dict[str, int]]: Test vector if found, else None.
        """
        # Initialize all net values to unknown (X)
        values = {name: SignalValue.X for name in self.circuit.nets}
        self._fault = fault
        good_value = SignalValue.ZERO if fault.stuck_at == 1 else SignalValue.ONE

        # If fault is on a primary input, set its value
        if fault.net in self.circuit.primary_inputs:
            values[fault.net] = good_value
        else:
            # Otherwise, justify the gate output
            if not self._justify_gate_output(fault.net, good_value, values):
                self._fault = None
                return None

        # If fault is on the stem, set D or D_BAR value
        if fault.sink is None:
            values[fault.net] = SignalValue.D if fault.stuck_at == 0 else SignalValue.D_BAR
        # Recursively search for a test vector
        success = self._d_alg_recursive(values, fault, depth=0, max_depth=max_depth)
        vector = self._extract_vector(values) if success else None
        self._fault = None
        return vector

    def _d_alg_recursive(
        self,
        values: Dict[str, SignalValue],
        fault: Fault,
        depth: int,
        max_depth: int,
    ) -> bool:
        """
        Recursive core of the D-Algorithm search.
        Args:
            values: Current net values.
            fault: Target fault.
            depth: Current recursion depth.
            max_depth: Maximum allowed depth.
        Returns:
            bool: True if a test vector is found, False otherwise.
        """
        if depth > max_depth:
            return False

        # Check if current assignment is valid
        if not self._imply_check(values, fault):
            return False

        # If error not at primary output, propagate further
        if not self._error_at_po(values):
            frontier = self._get_d_frontier(values)
            if not frontier:
                return False

            # Try each gate in the D-frontier
            for gate_name in frontier:
                gate = self.circuit.gates.get(gate_name)
                if gate is None:
                    continue
                saved = dict(values)
                ctrl = self._get_controlling(gate.type.lower())
        # ...existing code...

                if ctrl is None:
                    if self._d_alg_recursive(values, fault, depth + 1, max_depth):
                        return True
                else:
                    non_ctrl = SignalValue.ZERO if ctrl == SignalValue.ONE else SignalValue.ONE
                    for inp in gate.inputs:
                        if self._get_value(values, inp, gate.name) == SignalValue.X:
                            values[inp] = non_ctrl
                    if self._d_alg_recursive(values, fault, depth + 1, max_depth):
                        return True

                values.update(saved)

            return False
        else:
            j_front = self._get_j_frontier(values)
            if not j_front:
                return True

            gate = self.circuit.gates.get(j_front[0])
            if gate is None:
                return True

            for inp in gate.inputs:
                if self._get_value(values, inp, gate.name) == SignalValue.X:
                    saved = dict(values)
                    for try_val in (SignalValue.ZERO, SignalValue.ONE):
                        values[inp] = try_val
                        if self._imply_check(values, fault):
                            if self._d_alg_recursive(values, fault, depth + 1, max_depth):
                                return True
                        values.update(saved)
                    return False

            return True

    def _justify_gate_output(
        self,
        gate_name: str,
        target_value: SignalValue,
        values: Dict[str, SignalValue],
    ) -> bool:
        gate = self.circuit.gates.get(gate_name)
        if gate is None:
            values[gate_name] = target_value
            return True

        gate_type = gate.type.lower()
        if gate_type in {"not", "inv", "inverter"}:
            if gate.inputs:
                values[gate.inputs[0]] = target_value.invert()
                return self._imply_check(values, self._fault)
            return False

        if gate_type in {"and", "nand"}:
            controlling = SignalValue.ZERO
            non_controlling = SignalValue.ONE
            if (gate_type == "and" and target_value == SignalValue.ONE) or (
                gate_type == "nand" and target_value == SignalValue.ZERO
            ):
                for inp in gate.inputs:
                    values[inp] = non_controlling
                return self._imply_check(values, self._fault)
            if gate.inputs:
                values[gate.inputs[0]] = controlling
                for inp in gate.inputs[1:]:
                    if self._get_value(values, inp, gate.name) == SignalValue.X:
                        values[inp] = non_controlling
                return self._imply_check(values, self._fault)
            return False

        if gate_type in {"or", "nor"}:
            controlling = SignalValue.ONE
            non_controlling = SignalValue.ZERO
            if (gate_type == "or" and target_value == SignalValue.ONE) or (
                gate_type == "nor" and target_value == SignalValue.ZERO
            ):
                if gate.inputs:
                    values[gate.inputs[0]] = controlling
                    for inp in gate.inputs[1:]:
                        if self._get_value(values, inp, gate.name) == SignalValue.X:
                            values[inp] = non_controlling
                return self._imply_check(values, self._fault)
            for inp in gate.inputs:
                values[inp] = non_controlling
            return self._imply_check(values, self._fault)

        return False

    def _imply_check(
        self,
        values: Dict[str, SignalValue],
        fault: Fault,
    ) -> bool:
        max_iterations = len(self._topo_order) + 10

        for _ in range(max_iterations):
            changed = False
            for gate_name in self._topo_order:
                gate = self.circuit.gates.get(gate_name)
                if gate is None:
                    continue
                if fault.net == gate.output:
                    continue
                inp_vals = [self._get_value(values, inp, gate_name) for inp in gate.inputs]
                new_val = self._evaluate_gate_value(gate.type, inp_vals)
                old_val = values.get(gate.output, SignalValue.X)
                if (
                    old_val != SignalValue.X
                    and new_val != SignalValue.X
                    and old_val != new_val
                ):
                    return False
                if new_val != SignalValue.X and new_val != old_val:
                    values[gate.output] = new_val
                    changed = True
            if not changed:
                break
        return True

    def _error_at_po(self, values: Dict[str, SignalValue]) -> bool:
        return any(
            values.get(po, SignalValue.X).is_faulty()
            for po in self.circuit.primary_outputs
        )

    def _get_d_frontier(self, values: Dict[str, SignalValue]) -> List[str]:
        frontier: List[str] = []
        for gate in self.circuit.gates.values():
            if not gate.inputs:
                continue
            has_d_in = any(self._get_value(values, inp, gate.name).is_faulty() for inp in gate.inputs)
            has_d_out = values.get(gate.output, SignalValue.X).is_faulty()
            if has_d_in and not has_d_out:
                frontier.append(gate.name)
        return frontier

    def _get_j_frontier(self, values: Dict[str, SignalValue]) -> List[str]:
        frontier: List[str] = []
        for gate in self.circuit.gates.values():
            if not gate.inputs:
                continue
            has_x = any(self._get_value(values, inp, gate.name) == SignalValue.X for inp in gate.inputs)
            out_not_x = values.get(gate.output, SignalValue.X) != SignalValue.X
            if has_x and out_not_x:
                frontier.append(gate.name)
        return frontier

    def _get_value(
        self,
        values: Dict[str, SignalValue],
        net: str,
        gate_name: Optional[str] = None,
    ) -> SignalValue:
        value = values.get(net, SignalValue.X)
        if self._is_fault_branch_input(net, gate_name):
            return self._fault_branch_value()
        return value

    def _is_fault_branch_input(
        self,
        net_name: str,
        gate_name: Optional[str],
    ) -> bool:
        return (
            self._fault is not None
            and gate_name is not None
            and self._fault.sink is not None
            and self._fault.sink == gate_name
            and net_name == self._fault.net
        )

    def _fault_branch_value(self) -> SignalValue:
        if self._fault is None:
            return SignalValue.X
        return SignalValue.D if self._fault.stuck_at == 0 else SignalValue.D_BAR

    @staticmethod
    def _get_controlling(gate_type: str) -> Optional[SignalValue]:
        if gate_type in {"and", "nand"}:
            return SignalValue.ZERO
        if gate_type in {"or", "nor"}:
            return SignalValue.ONE
        return None

    def _evaluate_gate_value(
        self,
        gate_type: str,
        inputs: List[SignalValue],
    ) -> SignalValue:
        gtype = gate_type.lower()
        if gtype in {"buf", "buffer"}:
            return inputs[0] if inputs else SignalValue.X
        if gtype in {"not", "inv", "inverter"}:
            if not inputs:
                return SignalValue.X
            return inputs[0].invert()
        if gtype in {"and", "nand"}:
            if not inputs:
                return SignalValue.X
            result = inputs[0]
            for value in inputs[1:]:
                result = signal_and(result, value)
            return result.invert() if gtype == "nand" else result
        if gtype in {"or", "nor"}:
            if not inputs:
                return SignalValue.X
            result = inputs[0]
            for value in inputs[1:]:
                result = signal_or(result, value)
            return result.invert() if gtype == "nor" else result
        return SignalValue.X

    def _extract_vector(self, values: Dict[str, SignalValue]) -> Dict[str, int]:
        vector: Dict[str, int] = {}
        for pi in self.circuit.primary_inputs:
            val = values.get(pi, SignalValue.X)
            if val == SignalValue.ZERO:
                vector[pi] = 0
            elif val == SignalValue.ONE:
                vector[pi] = 1
            elif val == SignalValue.D:
                vector[pi] = 1
            elif val == SignalValue.D_BAR:
                vector[pi] = 0
            else:
                vector[pi] = 0
        return vector

    def _compute_topological_order(self) -> List[str]:
        graph: Dict[str, List[str]] = {name: [] for name in self.circuit.gates}
        indegree: Dict[str, int] = {name: 0 for name in self.circuit.gates}

        for gate in self.circuit.gates.values():
            for inp in gate.inputs:
                source = self.circuit.nets[inp].source
                if source in graph:
                    graph[source].append(gate.name)
                    indegree[gate.name] += 1

        queue = deque([name for name, deg in indegree.items() if deg == 0])
        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in graph.get(node, []):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.circuit.gates):
            raise ValueError("Circuit contains cycles; unable to run D-Algorithm")

        return order
