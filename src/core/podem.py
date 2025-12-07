from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from models import Circuit, Fault, Gate


class PodemEngine:
    """
    PODEM test generation for single stuck-at faults.
    Implements the PODEM algorithm for ATPG.
    """

    def __init__(self, circuit: Circuit):
        """
        Initialize the PODEM engine with a circuit.
        Args:
            circuit: Circuit object to operate on.
        """
        self.circuit = circuit
        self._topological_order = self._topological_sort()

    def find_test(self, fault: Fault) -> Optional[Dict[str, int]]:
        """
        Attempt to find a test vector that detects the given fault using PODEM.
        Args:
            fault: Fault to target.
        Returns:
            Optional[Dict[str, int]]: Test vector if found, else None.
        """
        assignments: Dict[str, int] = {}
        seen_states: Set[FrozenSet[Tuple[str, int]]] = set()
        values = self._imply(assignments, fault)
        if values and self._podem(assignments, values, fault, seen_states):
            return {pi: assignments.get(pi, 0) for pi in self.circuit.primary_inputs}
        return None

    # ------------------------------------------------------------------
    # Core recursive search
    # ------------------------------------------------------------------

    def _podem(
        self,
        assignments: Dict[str, int],
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
        seen_states: Set[FrozenSet[Tuple[str, int]]],
    ) -> bool:
        """
        Recursive core of the PODEM search.
        Args:
            assignments: Current PI assignments.
            values: Current net values.
            fault: Target fault.
            seen_states: Set of visited assignment states.
        Returns:
            bool: True if a test vector is found, False otherwise.
        """
        if not values:
            return False

        state = frozenset(assignments.items())
        if state in seen_states:
            return False
        seen_states.add(state)

        # Check if fault is propagated to output
        if self._is_fault_propagated(values):
            return True

        fault_val = values.get(fault.net, (None, None))
        if not self._is_d_or_dbar(fault_val):
            desired = 1 - fault.stuck_at
            good_val, _ = fault_val
            if good_val is not None and good_val != desired:
                return False

        fault_activated = self._is_fault_activated(values, fault)
        sentinel = None
        if fault_activated:
            sentinel = self._select_d_frontier(values, fault)
            if sentinel is None:
                return False

        objective = self._get_objective(values, fault, sentinel)
        if objective is None:
            return False
        # ...existing code...

        objective_net, objective_val = objective
        pi, pi_val = self._backtrace(objective_net, objective_val, values, assignments)
        if pi not in self.circuit.primary_inputs:
            return False
        original = assignments.get(pi)

        if original is not None and original != pi_val:
            return False
        assignments[pi] = pi_val
        values = self._imply(assignments, fault)
        if self._podem(assignments, values, fault, seen_states):
            return True

        if original is not None:
            return False
        assignments[pi] = 1 - pi_val
        values = self._imply(assignments, fault)
        if self._podem(assignments, values, fault, seen_states):
            return True

        if original is None:
            assignments.pop(pi, None)
        else:
            assignments[pi] = original
        return False

    # ------------------------------------------------------------------
    # Objective selection
    # ------------------------------------------------------------------

    def _get_objective(
        self,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
        frontier_gate: Optional[Gate] = None,
    ) -> Optional[Tuple[str, int]]:
        if not self._is_fault_activated(values, fault):
            desired = 1 - fault.stuck_at
            return fault.net, desired

        frontier_gate = frontier_gate or self._select_d_frontier(values, fault)
        if frontier_gate is None or not frontier_gate.inputs:
            return None

        target_input = frontier_gate.inputs[0]
        for inp in frontier_gate.inputs:
            if not self._is_d_or_dbar(self._gate_input_value(frontier_gate, inp, values, fault)):
                target_input = inp
                break

        non_ctrl = self._non_controlling_value(frontier_gate.type)
        return target_input, non_ctrl

    def _select_d_frontier(
        self,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
    ) -> Optional[Gate]:
        for gate in self.circuit.gates.values():
            good_out, faulty_out = values.get(gate.output, (None, None))
            if not (good_out is None or faulty_out is None):
                continue
            for inp in gate.inputs:
                if self._is_d_or_dbar(self._gate_input_value(gate, inp, values, fault)):
                    return gate
        return None

    def _gate_input_value(
        self,
        gate: Gate,
        net_name: str,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
    ) -> Tuple[Optional[int], Optional[int]]:
        good_val, faulty_val = values.get(net_name, (None, None))
        if fault.sink and gate.name == fault.sink and net_name == fault.net:
            faulty_val = fault.stuck_at
        return good_val, faulty_val

    def _is_fault_activated(
        self,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
    ) -> bool:
        if self._is_d_or_dbar(values.get(fault.net, (None, None))):
            return True
        if fault.sink is None:
            return False
        sink_gate = self.circuit.gates.get(fault.sink)
        if sink_gate is None:
            return False
        for inp in sink_gate.inputs:
            if inp != fault.net:
                continue
            if self._is_d_or_dbar(self._gate_input_value(sink_gate, inp, values, fault)):
                return True
        return False

    # ------------------------------------------------------------------
    # Backtrace and assignment
    # ------------------------------------------------------------------

    def _backtrace(
        self,
        net: str,
        value: int,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        assignments: Dict[str, int],
    ) -> Tuple[str, int]:
        current_net = net
        desired = value

        while current_net not in self.circuit.primary_inputs:
            source = self.circuit.nets[current_net].source
            if source is None:
                break
            gate = self.circuit.gates[source]
            gate_type = gate.type.lower()
            inverted = gate_type in {"nand", "nor", "not", "inv", "inverter"}
            if inverted:
                desired ^= 1

            if not gate.inputs:
                break
            candidate: Optional[str] = None
            fallback = gate.inputs[0]
            for inp in gate.inputs:
                assigned = assignments.get(inp)
                if assigned is None:
                    candidate = inp
                    break
                if assigned == desired and candidate is None:
                    candidate = inp
            current_net = candidate or fallback

        return current_net, desired

    def _imply(
        self,
        assignments: Dict[str, int],
        fault: Fault,
    ) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
        values: Dict[str, Tuple[Optional[int], Optional[int]]] = {}
        for pi in self.circuit.primary_inputs:
            if pi in assignments:
                assigned = assignments[pi]
                faulty_val = assigned
                if fault.sink is None and pi == fault.net:
                    faulty_val = fault.stuck_at
                values[pi] = (assigned, faulty_val)
            else:
                faulty_val = fault.stuck_at if fault.sink is None and pi == fault.net else None
                values[pi] = (None, faulty_val)

        for gate_name in self._topological_order:
            gate = self.circuit.gates[gate_name]
            input_pairs = [values.get(inp, (None, None)) for inp in gate.inputs]
            good_inputs = [pair[0] for pair in input_pairs]
            faulty_inputs: List[Optional[int]] = []
            for inp, pair in zip(gate.inputs, input_pairs):
                if fault.sink is not None and inp == fault.net and gate.name == fault.sink:
                    faulty_inputs.append(fault.stuck_at)
                else:
                    faulty_inputs.append(pair[1])

            good_out = self._evaluate_gate(gate.type, good_inputs)
            faulty_out = self._evaluate_gate(gate.type, faulty_inputs)
            if fault.sink is None and gate.output == fault.net:
                faulty_out = fault.stuck_at
            values[gate.output] = (good_out, faulty_out)

        return values

    @staticmethod
    def _evaluate_gate(gate_type: str, inputs: List[Optional[int]]) -> Optional[int]:
        gtype = gate_type.lower()
        if gtype in {"buf", "buffer"}:
            return inputs[0] if inputs else None
        if gtype in {"not", "inv", "inverter"}:
            if not inputs:
                return None
            val = inputs[0]
            return None if val is None else 1 - val

        inverted = gtype in {"nand", "nor"}
        base_type = "and" if gtype in {"and", "nand"} else "or" if gtype in {"or", "nor"} else None
        if base_type is None:
            raise ValueError(f"Unsupported gate type: {gate_type}")
        if not inputs:
            return None

        ctrl = 0 if base_type == "and" else 1
        non_ctrl = 1 - ctrl

        if any(val == ctrl for val in inputs):
            base_out: Optional[int] = ctrl
        elif all(val == non_ctrl for val in inputs):
            base_out = non_ctrl
        elif any(val is None for val in inputs):
            base_out = None
        else:
            base_out = None

        if inverted and base_out is not None:
            return 1 - base_out
        return base_out

    # ------------------------------------------------------------------
    # Utility checks
    # ------------------------------------------------------------------

    @staticmethod
    def _is_d_or_dbar(value: Tuple[Optional[int], Optional[int]]) -> bool:
        good, faulty = value
        return good is not None and faulty is not None and good != faulty

    def _is_fault_propagated(
        self, values: Dict[str, Tuple[Optional[int], Optional[int]]]
    ) -> bool:
        for po in self.circuit.primary_outputs:
            good, faulty = values.get(po, (None, None))
            if good in {0, 1} and faulty in {0, 1} and good != faulty:
                return True
        return False

    @staticmethod
    def _non_controlling_value(gate_type: str, desired: Optional[int] = None) -> int:
        gate_type = gate_type.lower()
        if gate_type in {"and", "nand"}:
            return 1
        if gate_type in {"or", "nor"}:
            return 0
        if gate_type in {"buf", "buffer", "not", "inv", "inverter"}:
            return desired if desired is not None else 0
        return desired if desired is not None else 0

    @staticmethod
    def _topological_sort_gate_inputs(graph: Dict[str, List[str]], indegree: Dict[str, int]) -> List[str]:
        """Topological sort helper."""
        from collections import deque

        queue = deque([name for name, deg in indegree.items() if deg == 0])
        order: List[str] = []
        while queue:
            gate_name = queue.popleft()
            order.append(gate_name)
            for neighbor in graph.get(gate_name, []):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)
        return order

    def _topological_sort(self) -> List[str]:
        graph: Dict[str, List[str]] = {name: [] for name in self.circuit.gates}
        indegree: Dict[str, int] = {name: 0 for name in self.circuit.gates}

        for gate in self.circuit.gates.values():
            for inp in gate.inputs:
                source = self.circuit.nets[inp].source
                if source in graph:
                    graph[source].append(gate.name)
                    indegree[gate.name] += 1

        order = self._topological_sort_gate_inputs(graph, indegree)
        if len(order) != len(self.circuit.gates):
            raise ValueError("Circuit contains cycles; unable to generate tests.")
        return order
