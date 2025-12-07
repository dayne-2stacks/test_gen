# Implements Boolean SAT solving for circuit fault analysis and test pattern generation.
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Sequence

from models import Circuit, Fault
from z3 import Bool, Not, Or, Solver, is_true, sat

Clause = List[int]



def _literal_satisfied(literal: int, assignment: Dict[int, bool]) -> bool:
    """
    Return whether a literal is true under the given partial assignment.
    """
    value = assignment.get(abs(literal), False)
    return value if literal > 0 else not value

def _clauses_satisfied(clauses: List[Clause], assignment: Dict[int, bool]) -> bool:
    """
    Check if all clauses are satisfied by the given assignment.
    """
    return all(any(_literal_satisfied(lit, assignment) for lit in clause) for clause in clauses)

def _generate_clause_library() -> List[Clause]:
    """
    Generate a library of example clauses for SAT problems.
    """
    base_literals = [1, -1, 2, -2]
    library: List[Clause] = [[lit] for lit in base_literals]
    library.extend([list(combo) for combo in combinations(base_literals, 2)])
    return library

class Z3Solver:
    """
    CNF solver backed by Z3 for faster SAT queries.
    """

    def __init__(self, clauses: List[Clause]):
        """
        Initialize the solver with a set of clauses.
        """
        self._clauses = clauses

    def solve(self) -> Optional[Dict[int, bool]]:
        """
        Attempt to solve the SAT problem.
        """
        # if no sat clauses, return empty assignment
        if not self._clauses:
            return {}

        solver = Solver()
        var_cache: Dict[int, Bool] = {}

        def get_var(idx: int) -> Bool:
            """
            Get or create a Z3 boolean variable for the given index.
            """
            existing = var_cache.get(idx)
            if existing is None:
                existing = Bool(f"v{idx}")
                var_cache[idx] = existing
            return existing

        # Add each clause to the Z3 solver
        for clause in self._clauses:
            if not clause:
                return None
            z3_clause = [
                get_var(abs(lit)) if lit > 0 else Not(get_var(abs(lit)))
                for lit in clause
            ]
            solver.add(Or(*z3_clause))

        # Check satisfiability
        if solver.check() != sat:
            return None

        model = solver.model()
        assignment: Dict[int, bool] = {}
        for idx, sym in var_cache.items():
            assignment[idx] = is_true(model.eval(sym, model_completion=True))
        return assignment


def run_boolean_sat_tests() -> None:
    """Exercise the Z3-backed solver on small CNFs to validate encoding."""
    library = _generate_clause_library()
    total = 1 << len(library)
    for mask in range(total):
        clauses = [library[idx] for idx in range(len(library)) if mask & (1 << idx)]
        result = Z3Solver(clauses).solve()
        if result is None:
            continue
        assert _clauses_satisfied(clauses, result), f"model does not satisfy {clauses}"
    print(f"Boolean SAT solver passed {total} small-CNF satisfiability checks.")


class CnfEncoder:
    """Builds CNF for good and faulty circuit copies."""

    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self._var_counter = 1
        self._name_to_var: Dict[str, int] = {}
        self._current_fault: Optional[Fault] = None

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

    def faulty_var(self, net: str, sink: Optional[str] = None) -> int:
        fault = self._current_fault
        if fault and fault.sink and net == fault.net and sink == fault.sink:
            return self._intern(f"fbranch:{net}->{sink}")
        if net in self.circuit.primary_inputs:
            if fault and fault.sink is None and net == fault.net:
                return self._intern(f"fpi:{net}")
            return self.pi_var(net)
        return self._intern(f"f:{net}")

    def new_aux(self, label: str) -> int:
        return self._intern(f"aux:{label}:{self._var_counter}")

    def build_fault_instance(self, fault: Fault) -> List[Clause]:
        self._current_fault = fault
        clauses: List[Clause] = []

        # Ensure primary inputs are interned before encoding.
        for pi in self.circuit.primary_inputs:
            self.pi_var(pi)

        for gate in self.circuit.gates.values():
            self._encode_gate(gate, faulty=False, clauses=clauses)
        for gate in self.circuit.gates.values():
            if fault.sink is None and gate.output == fault.net:
                continue
            self._encode_gate(gate, faulty=True, clauses=clauses)

        faulty_var = (
            self.faulty_var(fault.net, sink=fault.sink)
            if fault.sink
            else self.faulty_var(fault.net)
        )
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
        self._current_fault = None
        return clauses

    def _encode_gate(self, gate, *, faulty: bool, clauses: List[Clause]) -> None:
        gate_type = gate.type.lower()
        out_var = self.faulty_var(gate.output) if faulty else self.good_var(gate.output)
        input_vars = [
            (
                self.faulty_var(inp, sink=gate.name)
                if faulty
                else self.good_var(inp)
            )
            for inp in gate.inputs
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
