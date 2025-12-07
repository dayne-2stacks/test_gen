from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from models import Circuit, Fault, Gate

class PodemEngine:
    """
    PODEM test generation for single stuck-at faults.
    """

    def __init__(self, circuit: Circuit):
        """
        Initialize the PODEM engine with a circuit.
        """
        self.circuit = circuit
        self._topological_order = self._topological_sort()
        self._last_d_frontier: List[Gate] = []
        self._last_j_frontier: List[Gate] = []

    def find_test(self, fault: Fault) -> Optional[Dict[str, int]]:
        """
        Attempt to find a test vector that detects the given fault using PODEM.
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

        objective_net, objective_val = objective
        pi_candidates = self._backtrace(objective_net, objective_val, values, assignments)
        if not pi_candidates:
            return False

        base_assignments = dict(assignments)
        for pi_net, pi_val in pi_candidates:
            if pi_net not in self.circuit.primary_inputs:
                continue
            if base_assignments.get(pi_net) is not None:
                continue
            for trial_val in (pi_val, 1 - pi_val):
                assignments.clear()
                assignments.update(base_assignments)
                assignments[pi_net] = trial_val
                updated_values = self._imply(assignments, fault)
                if self._podem(assignments, updated_values, fault, seen_states):
                    return True

        assignments.clear()
        assignments.update(base_assignments)
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

        self._collect_j_frontier(values, fault)
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
        frontier = self._collect_d_frontier(values, fault)
        return frontier[0] if frontier else None

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
        _values: Dict[str, Tuple[Optional[int], Optional[int]]],
        assignments: Dict[str, int],
    ) -> List[Tuple[str, int]]:
        paths: List[Tuple[str, int]] = []
        seen: Set[Tuple[str, int]] = set()

        def dfs(current_net: str, required: int) -> None:
            key = (current_net, required)
            if key in seen:
                return
            seen.add(key)
            if current_net in self.circuit.primary_inputs:
                paths.append(key)
                return
            net_obj = self.circuit.nets.get(current_net)
            if net_obj is None or net_obj.source is None:
                return
            gate = self.circuit.gates.get(net_obj.source)
            if gate is None or not gate.inputs:
                return

            gate_type = gate.type.lower()
            if gate_type in {"buf", "buffer"}:
                dfs(gate.inputs[0], required)
                return
            if gate_type in {"not", "inv", "inverter"}:
                dfs(gate.inputs[0], 1 - required)
                return

            inverted = gate_type in {"nand", "nor"}
            next_value = required ^ 1 if inverted else required
            ordered_inputs = self._order_backtrace_inputs(gate, next_value, assignments)
            for inp in ordered_inputs:
                dfs(inp, next_value)

        dfs(net, value)
        return paths

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

    def _order_backtrace_inputs(
        self, gate: Gate, desired: int, assignments: Dict[str, int]
    ) -> List[str]:
        if not gate.inputs:
            return []
        unassigned: List[str] = []
        matching: List[str] = []
        others: List[str] = []
        for inp in gate.inputs:
            assigned = assignments.get(inp)
            if assigned is None:
                unassigned.append(inp)
            elif assigned == desired:
                matching.append(inp)
            else:
                others.append(inp)

        ordered: List[str] = []
        for group in (unassigned, matching, others):
            for net in group:
                if net not in ordered:
                    ordered.append(net)
        return ordered or gate.inputs[:]

    def _collect_d_frontier(
        self,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
    ) -> List[Gate]:
        frontier: List[Gate] = []
        for gate in self.circuit.gates.values():
            good_out, faulty_out = values.get(gate.output, (None, None))
            if good_out is not None and faulty_out is not None:
                continue
            for inp in gate.inputs:
                if self._is_d_or_dbar(self._gate_input_value(gate, inp, values, fault)):
                    frontier.append(gate)
                    break
        self._last_d_frontier = frontier
        return frontier

    def _collect_j_frontier(
        self,
        values: Dict[str, Tuple[Optional[int], Optional[int]]],
        fault: Fault,
    ) -> List[Gate]:
        frontier: List[Gate] = []
        for gate in self.circuit.gates.values():
            good_out, faulty_out = values.get(gate.output, (None, None))
            if good_out is not None and faulty_out is not None:
                continue
            if any(
                self._is_d_or_dbar(self._gate_input_value(gate, inp, values, fault))
                for inp in gate.inputs
            ):
                continue
            frontier.append(gate)
        self._last_j_frontier = frontier
        return frontier

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
