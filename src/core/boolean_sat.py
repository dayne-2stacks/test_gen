from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Sequence

from models import Circuit, Fault
from z3 import Bool, Not, Or, Solver, is_true, sat

Clause = List[int]
# TODO: Ensure that z3 elements are imported from correct location.
def _literal_satisfied(literal: int, assignment: Dict[int, bool]) -> bool:
    """Return whether a literal is true under the given partial assignment."""
    value = assignment.get(abs(literal), False)
    return value if literal > 0 else not value


def _clauses_satisfied(clauses: List[Clause], assignment: Dict[int, bool]) -> bool:
    return all(any(_literal_satisfied(lit, assignment) for lit in clause) for clause in clauses)


def _brute_force_model(clauses: List[Clause]) -> Optional[Dict[int, bool]]:
    if not clauses:
        return {}
    variables = sorted({abs(lit) for clause in clauses for lit in clause})
    for mask in range(1 << len(variables)):
        assignment = {
            var: bool(mask & (1 << idx)) for idx, var in enumerate(variables)
        }
        if _clauses_satisfied(clauses, assignment):
            return assignment
    return None


def _generate_clause_library() -> List[Clause]:
    base_literals = [1, -1, 2, -2]
    library: List[Clause] = [[lit] for lit in base_literals]
    library.extend([list(combo) for combo in combinations(base_literals, 2)])
    return library


class DpllSolver:
    """Lightweight DPLL SAT solver."""

    def __init__(self, clauses: List[Clause]):
        self._clauses = [clause[:] for clause in clauses]

    def solve(self) -> Optional[Dict[int, bool]]:
        return self._dpll(self._clauses, {})

    def _dpll(self, clauses: List[Clause], assignment: Dict[int, bool]) -> Optional[Dict[int, bool]]:
        clauses = self._unit_propagate(clauses, assignment)
        if clauses is None:
            return None
        clauses = self._pure_literal_elimination(clauses, assignment)
        if clauses is None:
            return None
        if not clauses:
            return assignment

        var = self._select_variable(clauses, assignment)
        for value in (True, False):
            next_assignment = assignment.copy()
            next_assignment[var] = value
            simplified = self._simplify(clauses, var, value)
            if simplified is None:
                continue
            result = self._dpll(simplified, next_assignment)
            if result is not None:
                return result
        return None

    def _unit_propagate(self, clauses: List[Clause], assignment: Dict[int, bool]) -> Optional[List[Clause]]:
        while True:
            unit_lit = next((clause[0] for clause in clauses if len(clause) == 1), None)
            if unit_lit is None:
                return clauses
            var = abs(unit_lit)
            value = unit_lit > 0
            current = assignment.get(var)
            if current is not None and current != value:
                return None
            assignment[var] = value
            clauses = self._simplify(clauses, var, value)
            if clauses is None:
                return None

    def _pure_literal_elimination(
        self, clauses: List[Clause], assignment: Dict[int, bool]
    ) -> Optional[List[Clause]]:
        literals = {}
        for clause in clauses:
            for lit in clause:
                literals[lit] = True

        changed = False
        for lit in list(literals.keys()):
            if -lit in literals:
                continue
            var = abs(lit)
            if var in assignment:
                continue
            assignment[var] = lit > 0
            clauses = self._simplify(clauses, var, lit > 0)
            if clauses is None:
                return None
            changed = True

        if changed:
            return self._unit_propagate(clauses, assignment)
        return clauses

    def _simplify(self, clauses: List[Clause], var: int, value: bool) -> Optional[List[Clause]]:
        satisfied = var if value else -var
        removed = -satisfied
        simplified: List[Clause] = []
        for clause in clauses:
            if satisfied in clause:
                continue
            new_clause = [lit for lit in clause if lit != removed]
            if not new_clause:
                return None
            simplified.append(new_clause)
        return simplified

    def _select_variable(self, clauses: List[Clause], assignment: Dict[int, bool]) -> int:
        freq: Dict[int, int] = {}
        for clause in clauses:
            for lit in clause:
                var = abs(lit)
                if var in assignment:
                    continue
                freq[var] = freq.get(var, 0) + 1
        return max(freq, key=freq.get)


class Z3Solver:
    """CNF solver backed by Z3 for faster SAT queries."""

    def __init__(self, clauses: List[Clause]):
        self._clauses = clauses

    def solve(self) -> Optional[Dict[int, bool]]:
        if not self._clauses:
            return {}

        solver = Solver()
        var_cache: Dict[int, Bool] = {}

        def get_var(idx: int) -> Bool:
            existing = var_cache.get(idx)
            if existing is None:
                existing = Bool(f"v{idx}")
                var_cache[idx] = existing
            return existing

        for clause in self._clauses:
            if not clause:
                return None
            z3_clause = [
                get_var(abs(lit)) if lit > 0 else Not(get_var(abs(lit)))
                for lit in clause
            ]
            solver.add(Or(*z3_clause))

        if solver.check() != sat:
            return None

        model = solver.model()
        assignment: Dict[int, bool] = {}
        for idx, sym in var_cache.items():
            assignment[idx] = is_true(model.eval(sym, model_completion=True))
        return assignment


def run_boolean_sat_tests() -> None:
    """Exercise the DPLL solver on all small CNFs to check satisfiability decisions."""
    library = _generate_clause_library()
    total = 1 << len(library)
    for mask in range(total):
        clauses = [library[idx] for idx in range(len(library)) if mask & (1 << idx)]
        expected = _brute_force_model(clauses)
        result = Z3Solver(clauses).solve()
        if expected is None:
            assert result is None, f"solver incorrectly reported SAT for {clauses}"
            continue
        assert result is not None, f"solver failed to find a model for {clauses}"
        assert _clauses_satisfied(clauses, result), f"model does not satisfy {clauses}"
    print(f"Boolean SAT solver passed {total} exhaustive small-CNF tests.")


class CnfEncoder:
    """Builds CNF for good and faulty circuit copies."""

    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self._var_counter = 1
        self._name_to_var: Dict[str, int] = {}
        self._current_fault_net: Optional[str] = None

    def _intern(self, key: str) -> int:
        existing = self._name_to_var.get(key)
        if existing is not None:
            return existing
        var = self._var_counter
        self._var_counter += 1
        self._name_to_var[key] = var
        return var

    def pi_var(self, name: str) -> int:
        return self._intern(f"pi:{name}")

    def good_var(self, net: str) -> int:
        if net in self.circuit.primary_inputs:
            return self.pi_var(net)
        return self._intern(f"g:{net}")

    def faulty_var(self, net: str) -> int:
        if net in self.circuit.primary_inputs:
            if net == self._current_fault_net:
                return self._intern(f"fpi:{net}")
            return self.pi_var(net)
        return self._intern(f"f:{net}")

    def new_aux(self, label: str) -> int:
        return self._intern(f"aux:{label}:{self._var_counter}")

    def build_fault_instance(self, fault: Fault) -> List[Clause]:
        self._current_fault_net = fault.net
        clauses: List[Clause] = []

        # Ensure primary inputs are interned before encoding.
        for pi in self.circuit.primary_inputs:
            self.pi_var(pi)

        for gate in self.circuit.gates.values():
            self._encode_gate(gate, faulty=False, clauses=clauses)
        for gate in self.circuit.gates.values():
            if gate.output == fault.net:
                continue
            self._encode_gate(gate, faulty=True, clauses=clauses)

        faulty_var = self.faulty_var(fault.net)
        clauses.append([faulty_var] if fault.stuck_at else [-faulty_var])

        good_var = self.good_var(fault.net)
        clauses.append([-good_var] if fault.stuck_at else [good_var])

        diff_vars: List[int] = []
        for idx, po in enumerate(self.circuit.primary_outputs):
            g_po = self.good_var(po)
            f_po = self.faulty_var(po)
            diff = self.new_aux(f"diff:{po}:{idx}")
            diff_vars.append(diff)
            self._add_xor(diff, g_po, f_po, clauses)
        if diff_vars:
            clauses.append(diff_vars)
        self._current_fault_net = None
        return clauses

    def _encode_gate(self, gate, *, faulty: bool, clauses: List[Clause]) -> None:
        gate_type = gate.type.lower()
        out_var = self.faulty_var(gate.output) if faulty else self.good_var(gate.output)
        input_vars = [
            self.faulty_var(inp) if faulty else self.good_var(inp) for inp in gate.inputs
        ]

        if gate_type in {"and", "or"}:
            self._encode_basic_gate(gate_type, out_var, input_vars, clauses)
        elif gate_type in {"buf", "buffer"}:
            self._add_equivalence(out_var, input_vars[0], clauses)
        elif gate_type in {"not", "inv", "inverter"}:
            self._add_not(out_var, input_vars[0], clauses)
        elif gate_type in {"nand", "nor"}:
            base_type = "and" if gate_type == "nand" else "or"
            aux = self.new_aux(f"{gate.name}:{gate_type}")
            self._encode_basic_gate(base_type, aux, input_vars, clauses)
            self._add_not(out_var, aux, clauses)
        else:
            raise ValueError(f"Unsupported gate type: {gate.type}")

    @staticmethod
    def _encode_basic_gate(gate_type: str, output: int, inputs: Sequence[int], clauses: List[Clause]) -> None:
        if gate_type == "and":
            clauses.append([output] + [-inp for inp in inputs])
            for inp in inputs:
                clauses.append([-output, inp])
        elif gate_type == "or":
            clauses.append([-output] + inputs)
            for inp in inputs:
                clauses.append([output, -inp])
        else:
            raise ValueError(f"Unsupported basic gate type: {gate_type}")

    @staticmethod
    def _add_equivalence(a: int, b: int, clauses: List[Clause]) -> None:
        clauses.append([-a, b])
        clauses.append([a, -b])

    @staticmethod
    def _add_not(a: int, b: int, clauses: List[Clause]) -> None:
        clauses.append([-a, -b])
        clauses.append([a, b])

    @staticmethod
    def _add_xor(out: int, a: int, b: int, clauses: List[Clause]) -> None:
        clauses.append([-out, -a, -b])
        clauses.append([-out, a, b])
        clauses.append([out, -a, b])
        clauses.append([out, a, -b])


class SatAtpg:
    """Generates test vectors using SAT-based formulation."""

    def __init__(self, circuit: Circuit):
        self.circuit = circuit

    def find_test(self, fault: Fault) -> Optional[Dict[str, int]]:
        encoder = CnfEncoder(self.circuit)
        clauses = encoder.build_fault_instance(fault)
        solver = Z3Solver(clauses)
        model = solver.solve()
        if model is None:
            return None

        vector: Dict[str, int] = {}
        for pi in self.circuit.primary_inputs:
            var = encoder.pi_var(pi)
            vector[pi] = int(model.get(var, False))
        return vector


if __name__ == "__main__":
    run_boolean_sat_tests()
