
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Set
from models import Circuit, Fault


def _fault_sort_key(fault: Fault) -> tuple[str, str, int]:
    """
    Sorting key for faults: sorts by net, sink, and stuck-at value.
    """
    return (fault.net, fault.sink or "", fault.stuck_at)


def _collapsed_fault_sets(
    result: "CollapseResult",
) -> tuple[Dict[Fault, List[Fault]], Dict[Fault, List[Fault]]]:
    """
    Build lookup tables for equivalence classes and dominance edges.
    """
    fault_to_rep = result.fault_to_representative
    surviving_reps = {cls.representative for cls in result.classes}

    # Map each equivalence class representative to its ultimate dominator.
    rep_dominator: Dict[Fault, Fault] = {}
    for dominated_fault, dominator_fault in result.dominated_faults.items():
        dominated_rep = fault_to_rep.get(dominated_fault, dominated_fault)
        dominator_rep = fault_to_rep.get(dominator_fault, dominator_fault)
        if dominated_rep != dominator_rep:
            rep_dominator[dominated_rep] = dominator_rep

    def _root(rep: Fault) -> Fault:
        """
        Find the dominator for a representative fault.
        """
        path = []
        while rep in rep_dominator:
            path.append(rep)
            rep = rep_dominator[rep]
        for node in path:
            rep_dominator[node] = rep
        return rep

    groups: Dict[Fault, List[Fault]] = defaultdict(list)
    dominated_groups: Dict[Fault, List[Fault]] = defaultdict(list)

    # Map faults to their equivalence class root
    for fault, eq_rep in fault_to_rep.items():
        root_rep = _root(eq_rep)
        if root_rep not in surviving_reps:
            continue
        if root_rep == eq_rep:
            groups[root_rep].append(fault)
        else:
            dominated_groups[root_rep].append(fault)

    for rep in surviving_reps:
        groups.setdefault(rep, [rep])

    return groups, dominated_groups


@dataclass(frozen=True)
class FaultClass:
    """Represents a collapsed fault class with a single representative."""

    representative: Fault
    members: List[Fault]


@dataclass
class CollapseResult:
    """Final artefact returned by the collapsing routine."""

    classes: List[FaultClass]
    dominated_faults: Dict[Fault, Fault]
    fault_to_representative: Dict[Fault, Fault]
    total_faults: int

    @property
    def collapsed_faults(self) -> List[Fault]:
        return [cls.representative for cls in self.classes]

def prepare_fault_collapsing_output(
    result: "CollapseResult",
) -> tuple["FaultCollapsingReport", List[str], List[str]]:
    """
    Normalize collapse results into printable/file-ready blocks.

    Returns:
        report: structured equivalence/dominance breakdown.
        total_fault_lines: sorted list of every enumerated fault as strings.
        summary_lines: formatted summary matching the standard collapse stdout.
    """
    report = build_fault_collapsing_report(result)
    total_fault_lines = [
        str(fault)
        for fault in sorted(result.fault_to_representative, key=_fault_sort_key)
    ]
    return report, total_fault_lines, report.summary_lines()

@dataclass
class FaultCollapsingReport:
    total_faults: int
    equivalence_classes: Dict[Fault, List[Fault]]
    dominance_relations: Dict[Fault, List[Fault]]
    dominance_edges: Dict[Fault, Fault]

    @property
    def collapsed_count(self) -> int:
        return len(self.equivalence_classes)

    @property
    def dominated_count(self) -> int:
        return len(self.dominance_edges)

    def equivalence_lines(self) -> List[str]:
        lines: List[str] = []
        for representative in sorted(self.equivalence_classes, key=_fault_sort_key):
            members = self.equivalence_classes[representative]
            ordered_members = [representative] + [fault for fault in members if fault != representative]
            lines.append(f"{representative}: " + " ".join(str(fault) for fault in ordered_members))
        return lines

    def dominance_lines(self) -> List[str]:
        lines: List[str] = []
        for dominator in sorted(self.dominance_relations, key=_fault_sort_key):
            dominated = self.dominance_relations[dominator]
            if dominated:
                lines.append(
                    f"{dominator} dominates: " + " ".join(str(fault) for fault in dominated)
                )
        return lines

    def summary_lines(self) -> List[str]:
        return [
            f"Total faults: {self.total_faults}",
            f"Collapsed fault classes: {self.collapsed_count}",
            f"Dominated fault classes removed: {self.dominated_count}",
            "",
            "Equivalent fault classes:",
            *(self.equivalence_lines() or ["<none>"]),
            "",
            "Dominating faults:",
            *(self.dominance_lines() or ["<none>"]),
        ]


def build_fault_collapsing_report(result: "CollapseResult") -> FaultCollapsingReport:
    """
    Construct an aggregate report for a collapsing run with equivalence and dominance info.
    """
    groups, dominated_groups = _collapsed_fault_sets(result)
    normalized_groups = {
        rep: sorted(set(members), key=_fault_sort_key) for rep, members in groups.items()
    }
    normalized_dominance = {
        rep: sorted(set(faults), key=_fault_sort_key) for rep, faults in dominated_groups.items()
    }
    return FaultCollapsingReport(
        total_faults=result.total_faults,
        equivalence_classes=normalized_groups,
        dominance_relations=normalized_dominance,
        dominance_edges=dict(result.dominated_faults),
    )


class FaultCollapser:
    """
    Collapse single stuck-at faults for a parsed circuit.

    Usage:
        collapser = FaultCollapser(circuit)
        result = collapser.collapse()
    """

    def __init__(self, circuit: Circuit):
        self.circuit = circuit
        self._faults: List[Fault] = []
        self._fault_set: Set[Fault] = set()
        self._uf: UnionFind | None = None
        self._fanout_nets = {
            name for name, net in circuit.nets.items() if len(net.sinks) > 1
        }
        self._fanout_branches: Dict[str, Set[str]] = {
            name: set(net.sinks) for name, net in circuit.nets.items() if len(net.sinks) > 1
        }

    def collapse(self) -> CollapseResult:
        self._faults = list(self._enumerate_faults())
        self._fault_set = set(self._faults)
        self._uf = UnionFind(self._faults)

        self._apply_equivalence_rules()
        classes = self._collect_classes()

        fault_to_rep_all = {
            fault: rep for rep, members in classes.items() for fault in members
        }
        dominance_report, dominated_classes = self._identify_dominated_faults(
            fault_to_rep_all
        )
        surviving_items = [
            (rep, members) for rep, members in classes.items() if rep not in dominated_classes
        ]
        surviving = [FaultClass(rep, members) for rep, members in surviving_items]
        fault_to_rep = {fault: rep for rep, members in classes.items() for fault in members}

        return CollapseResult(
            classes=sorted(
                surviving,
                key=lambda cls: (
                    cls.representative.net,
                    cls.representative.sink or "",
                    cls.representative.stuck_at,
                ),
            ),
            dominated_faults=dominance_report,
            fault_to_representative=fault_to_rep,
            total_faults=len(self._faults),
        )

    # ------------------------------------------------------------------
    # Fault enumeration
    # ------------------------------------------------------------------

    def _enumerate_faults(self) -> Iterable[Fault]:
        for net_name, net in self.circuit.nets.items():
            yield self._fault_for(net_name, 0)
            yield self._fault_for(net_name, 1)
            if net_name in self._fanout_nets:
                for sink in net.sinks:
                    yield Fault(net=net_name, stuck_at=0, sink=sink)
                    yield Fault(net=net_name, stuck_at=1, sink=sink)

    # ------------------------------------------------------------------
    # Equivalence collapsing
    # ------------------------------------------------------------------

    def _apply_equivalence_rules(self) -> None:
        assert self._uf is not None
        for gate in self.circuit.gates.values():
            gate_type = gate.type.lower()
            inputs = gate.inputs
            output = gate.output

            if gate_type in {"not", "inv", "inverter"}:
                self._union(
                    output,
                    1,
                    inputs[0],
                    0,
                    sink_b=self._input_sink(inputs[0], gate.name),
                )
                self._union(
                    output,
                    0,
                    inputs[0],
                    1,
                    sink_b=self._input_sink(inputs[0], gate.name),
                )
                continue

            if gate_type in {"buf", "buffer"}:
                self._union(
                    output,
                    0,
                    inputs[0],
                    0,
                    sink_b=self._input_sink(inputs[0], gate.name),
                )
                self._union(
                    output,
                    1,
                    inputs[0],
                    1,
                    sink_b=self._input_sink(inputs[0], gate.name),
                )
                continue

            characteristics = self._gate_characteristics(gate_type)
            if characteristics:
                non_controlling, inverted = characteristics
                controlling = 1 - non_controlling
                self._union_inputs(inputs, stuck_value=controlling, gate_name=gate.name)

                output_value = controlling ^ inverted
                for inp in inputs:
                    self._union(
                        inp,
                        controlling,
                        output,
                        output_value,
                        sink_a=self._input_sink(inp, gate.name),
                    )
                continue

    def _union_inputs(self, nets: List[str], *, stuck_value: int, gate_name: str) -> None:
        for left, right in combinations(nets, 2):
            self._union(
                left,
                stuck_value,
                right,
                stuck_value,
                sink_a=self._input_sink(left, gate_name),
                sink_b=self._input_sink(right, gate_name),
            )

    def _union(
        self,
        net_a: str,
        sa_a: int,
        net_b: str,
        sa_b: int,
        *,
        sink_a: str | None = None,
        sink_b: str | None = None,
    ) -> None:
        assert self._uf is not None
        fault_a = self._fault_for(net_a, sa_a, sink_a)
        fault_b = self._fault_for(net_b, sa_b, sink_b)
        if fault_a in self._uf and fault_b in self._uf:
            self._uf.union(fault_a, fault_b)

    def _fault_for(self, net: str, stuck_at: int, sink: str | None = None) -> Fault:
        if sink:
            sinks = self._fanout_branches.get(net)
            if not sinks or sink not in sinks:
                sink = None
        return Fault(net=net, stuck_at=stuck_at, sink=sink)

    def _input_sink(self, net: str, sink_gate: str) -> str | None:
        sinks = self._fanout_branches.get(net)
        if sinks and sink_gate in sinks:
            return sink_gate
        return None

    @staticmethod
    def _gate_characteristics(gate_type: str) -> tuple[int, int] | None:
        """
        Returns the non-controlling value and inversion flag for AND/OR family gates.

        non_controlling: 1 for AND/NAND, 0 for OR/NOR
        inverted: 1 for NAND/NOR, 0 otherwise
        """
        if gate_type in {"and", "nand"}:
            return 1, int(gate_type == "nand")
        if gate_type in {"or", "nor"}:
            return 0, int(gate_type == "nor")
        return None

    def _collect_classes(self) -> Dict[Fault, List[Fault]]:
        assert self._uf is not None
        groups: Dict[Fault, List[Fault]] = defaultdict(list)
        for fault in self._faults:
            rep = self._uf.find(fault)
            groups[rep].append(fault)
        return groups

    @staticmethod
    def _resolve_dominator(rep: Fault, dominated_map: Dict[Fault, Fault]) -> Fault:
        while rep in dominated_map:
            rep = dominated_map[rep]
        return rep

    # ------------------------------------------------------------------
    # Dominance pruning
    # ------------------------------------------------------------------

    def _identify_dominated_faults(
        self,
        fault_to_rep: Dict[Fault, Fault],
    ) -> tuple[Dict[Fault, Fault], Dict[Fault, Fault]]:
        assert self._fault_set
        report_map: Dict[Fault, Fault] = {}
        dominated_classes: Dict[Fault, Fault] = {}

        def _register_dominance(dominated: Fault, dominator: Fault) -> bool:
            dominated_rep = fault_to_rep.get(dominated)
            dominator_rep = fault_to_rep.get(dominator)
            if not dominated_rep or not dominator_rep or dominated_rep == dominator_rep:
                return False

            report_map.setdefault(dominated_rep, dominator)
            dominated_classes.setdefault(dominated_rep, dominator)
            return True

        for gate in self.circuit.gates.values():
            gate_type = gate.type.lower()
            inputs = gate.inputs
            output = gate.output

            characteristics = self._gate_characteristics(gate_type)
            if not characteristics:
                continue

            non_controlling, inverted = characteristics
            controlling = 1 - non_controlling

            output_dominated_value = non_controlling ^ inverted
            output_fault = self._fault_for(output, output_dominated_value)
            if output_fault in self._fault_set:
                for inp in inputs:
                    input_fault = self._fault_for(
                        inp, non_controlling, self._input_sink(inp, gate.name)
                    )
                    if input_fault not in self._fault_set:
                        continue
                    if _register_dominance(output_fault, input_fault):
                        break

            output_dominator_value = controlling ^ inverted
            output_fault_control = self._fault_for(output, output_dominator_value)
            if output_fault_control in self._fault_set:
                for inp in inputs:
                    victim_fault = self._fault_for(
                        inp, controlling, self._input_sink(inp, gate.name)
                    )
                    if victim_fault not in self._fault_set:
                        continue
                    _register_dominance(victim_fault, output_fault_control)
        return report_map, dominated_classes


class UnionFind:
    """A lightweight union-find implementation keyed by hashable items."""

    def __init__(self, items: Iterable[Fault]):
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def __contains__(self, item: Fault) -> bool:
        return item in self.parent

    def find(self, item: Fault) -> Fault:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a: Fault, b: Fault) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return

        rank_a = self.rank[root_a]
        rank_b = self.rank[root_b]
        if rank_a < rank_b:
            self.parent[root_a] = root_b
        elif rank_a > rank_b:
            self.parent[root_b] = root_a
        else:
            self.parent[root_b] = root_a
            self.rank[root_a] += 1


def format_collapsed_faults(result: CollapseResult) -> List[str]:
    """
    Produce a human-friendly listing of collapsed fault classes.

    Each line contains the representative fault followed by the other
    faults that were collapsed into the same class (if any) plus any
    faults it dominates listed separately.
    """
    groups, dominated_groups = _collapsed_fault_sets(result)

    def sort_key(fault: Fault) -> tuple[str, str, int]:
        return (fault.net, fault.sink or "", fault.stuck_at)

    lines: List[str] = []
    for representative in sorted(groups, key=sort_key):
        equivalents = sorted(groups[representative], key=sort_key)
        dominated = sorted(dominated_groups.get(representative, []), key=sort_key)
        parts = [" ".join(str(fault) for fault in equivalents)]
        if dominated:
            parts.append("doms {" + " ".join(str(fault) for fault in dominated) + "}")
        lines.append(f"{representative}: " + " ".join(parts).strip())
    return lines
