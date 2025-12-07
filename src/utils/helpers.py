from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Collection, Dict, List, Optional, Sequence, Tuple

from core import (
    CollapseResult,
    DAlgorithmEngine,
    FaultSimulator,
    PodemEngine,
    SatAtpg,
)
from models import Circuit, Fault



class Stage(Enum):
    """
    Number stages of ATG processing.
    """
    PARSE = auto()
    COLLAPSE = auto()
    SIMULATE = auto()
    D_ALGO = auto()
    PODEM = auto()
    SAT = auto()
    
# A class that manages all stages of the ATG program

class StageManager:
    """
    Manages the workflow and state for all ATG stages. Handles dependencies, state, and execution for each stage.
    """
    def __init__(
        self,
        file_path: str,
        stage_handlers: Dict[Stage, Callable[..., Any]],
    ):
        # Set file path environment
        self.file_path = file_path
        # Ensure all required stage handlers are provided
        missing = [stage.name for stage in Stage if stage not in stage_handlers]
        if missing:
            raise ValueError(f"Missing handlers for stages: {', '.join(missing)}")

        # Handlers for each stage
        self._parse_handler = stage_handlers[Stage.PARSE]
        self._collapse_handler = stage_handlers[Stage.COLLAPSE]
        self._simulate_handler = stage_handlers[Stage.SIMULATE]
        self._d_algorithm_handler = stage_handlers[Stage.D_ALGO]
        self._podem_handler = stage_handlers[Stage.PODEM]
        self._sat_handler = stage_handlers[Stage.SAT]

        # Internal state for each stage
        self._circuit = None
        self._collapse_result = None
        self._simulation_result = None
        self._podem_result = None
        self._sat_result = None
        self._d_algorithm_result = None

        # Dependencies required before running each stage
        self._dependencies: Dict[Stage, tuple[Stage, ...]] = {
            Stage.COLLAPSE: (Stage.PARSE,),
            Stage.SIMULATE: (Stage.COLLAPSE,),
            Stage.D_ALGO: (Stage.COLLAPSE,),
            Stage.PODEM: (Stage.COLLAPSE,),
            Stage.SAT: (Stage.COLLAPSE,),
        }
        
        # Dict of handlers to implement stage specific tasks
        self._handlers: Dict[Stage, Callable[[], None]] = {
            Stage.PARSE: self._handle_parse,
            Stage.COLLAPSE: self._handle_collapse,
            Stage.SIMULATE: self._handle_simulate,
            Stage.D_ALGO: self._handle_d_algorithm,
            Stage.PODEM: self._handle_podem,
            Stage.SAT: self._handle_sat,
        }
        

    def ensure(self, stage: Stage, *, force: bool = False) -> None:
        """ Main function that ensures all dependency code has been ran before running stage code"""
        for dependency in self._dependencies.get(stage, ()):
            self.ensure(dependency)
        # logic to optionally rerun a specific stage
        if force or not self._is_stage_completed(stage):
            self._handlers[stage]()

    def clear(self) -> None:
        """Clear the state of the stage manager"""
        self._circuit = None
        self._collapse_result = None
        self._simulation_result = None
        self._podem_result = None
        self._sat_result = None
        self._d_algorithm_result = None
    
    def set_file_path(self, file_path: str) -> None:
        """Helper to set the file path and clear state if changed"""
        if file_path != self.file_path:
            self.file_path = file_path
            self.clear()

    def set_simulation_result(self, result: Any) -> None:
        """Stores the. resuult of a simulation"""
        self._simulation_result = result
    
    def _is_stage_completed(self, stage: Stage) -> bool:
        """Check if dependency structures from a stage is already generated"""
        if stage == Stage.PARSE:
            return self._circuit is not None
        if stage == Stage.COLLAPSE:
            return self._collapse_result is not None
        if stage == Stage.SIMULATE:
            return self._simulation_result is not None
        if stage == Stage.D_ALGO:
            return False
        if stage == Stage.PODEM:
            return self._podem_result is not None
        if stage == Stage.SAT:
            return self._sat_result is not None
        return False
    
    def _handle_parse(self) -> None:
        """ Use parse handler to get circuit definition"""
        circuit = self._parse_handler(self.file_path)
        if circuit is None:
            self._circuit = None
            self._collapse_result = None
            self._simulation_result = None
            self._podem_result = None
            self._sat_result = None
            self._d_algorithm_result = None
        else:
            self._circuit = circuit
            self._d_algorithm_result = None
    
    def _handle_collapse(self) -> None:
        """ Use collapse handler to get collapsed faults"""
        circuit, collapse_result = self._collapse_handler(self._circuit, self.file_path)
        # update circuit and collapsed faults if any is returned
        if circuit is not None:
            self._circuit = circuit
        if collapse_result is None:
            self._collapse_result = None
            self._simulation_result = None
            self._podem_result = None
            self._sat_result = None
            self._d_algorithm_result = None
        else:
            self._collapse_result = collapse_result
            self._podem_result = None
            self._sat_result = None
            self._d_algorithm_result = None
    
    def _handle_simulate(self) -> None:
        # Run the handler for simulation
        self._simulation_result = self._simulate_handler(self._circuit, self._collapse_result)
    
    def _handle_d_algorithm(self) -> None:
        self._d_algorithm_result = self._d_algorithm_handler(
            self._circuit, self._collapse_result
        )

    def _handle_podem(self) -> None:
        # Run the handler for podem
        self._podem_result = self._podem_handler(self._circuit, self._collapse_result)

    def _handle_sat(self) -> None:
        # Run the handler for sat
        self._sat_result = self._sat_handler(self._circuit, self._collapse_result)
    
        
    # Accessors so menu handlers can read results
    @property
    def circuit(self):
        return self._circuit

    @property
    def collapse_result(self):
        return self._collapse_result

    @property
    def simulation_result(self):
        return self._simulation_result

    @property
    def podem_result(self):
        return self._podem_result

    @property
    def sat_result(self):
        return self._sat_result

    @property
    def d_algorithm_result(self):
        return self._d_algorithm_result


@dataclass(frozen=True)
class TestVector:
    fault: Fault
    vector: Optional[Dict[str, int]]
    detected_faults: Tuple[Fault, ...]


class AtpgEngine:
    """ATPG driver that can run D-Algorithm, PODEM, or SAT in manual or automatic modes."""

    def __init__(
        self,
        circuit: Circuit,
        collapse_result: CollapseResult,
        algorithm: Any,
    ):
        if circuit is None or collapse_result is None:
            raise ValueError("ATPG engine requires a parsed circuit and collapsed faults.")
        self.circuit = circuit
        self.collapse_result = collapse_result
        self._fault_pool: Tuple[Fault, ...] = tuple(collapse_result.collapsed_faults)
        self._simulator = FaultSimulator(circuit, collapse_result)
        self._engine = self._select_algorithm(algorithm)

    def manual(self, faults: Sequence[Fault]) -> List[TestVector]:
        """Generate vectors for explicitly provided faults."""
        # Get list of active faults from the fault pool
        active_faults = set(self._fault_pool)
        results: List[TestVector] = []
        # for each fault, generate a test vector and simulate detected faults
        for fault in faults:
            target = self._representative(fault)
            vector = self._engine.find_test(target)
            detected = self._simulate_detected(vector, active_faults, target)
            results.append(TestVector(target, vector, detected))
        return results

    def automatic(self) -> List[TestVector]:
        """Cover the collapsed fault list, dropping detected faults as vectors are found."""
        # lists to keep track of faults to be tested
        remaining_stack = list(self._fault_pool)
        remaining_active = set(self._fault_pool)
        results: List[TestVector] = []
        # while there are still faults to process select a fault and generate a test vector
        while remaining_stack:
            fault = remaining_stack.pop()
            if fault not in remaining_active:
                continue

            remaining_active.discard(fault)
            vector = self._engine.find_test(fault)
            detected = self._simulate_detected(vector, remaining_active, fault)
            #  if detected faults, remove them from the remaining active set
            if detected:
                for detected_fault in detected:
                    remaining_active.discard(detected_fault)
            results.append(TestVector(fault, vector, detected))
        return results

    def _simulate_detected(
        self,
        vector: Optional[Dict[str, int]],
        candidate_faults: Collection[Fault],
        target: Fault,
    ) -> Tuple[Fault, ...]:
        """Simulate the given vector and return detected faults from the candidate set."""
        # if no test vector, return empty value
        if vector is None:
            return ()
        # Prepare the list of faults to simulate
        if candidate_faults:
            faults = list(candidate_faults)
            # if target fault is not in candidate faults, add it
            if target not in candidate_faults:
                faults.append(target)
        else:
            faults = [target]
        # Run the fault simulation with the prepared fault list
        report = self._simulator.run(vector, faults=faults)
        return tuple(report.detected_faults)
     
    def _representative(self, fault: Fault) -> Fault:
        """ Get the representative fault from the collapsed set."""
        return self.collapse_result.fault_to_representative.get(fault, fault)

    def _select_algorithm(self, algorithm: Any) -> Any:
        """Select between D-Algorithm, PODEM, or SAT ATPG algorithms."""
        if isinstance(algorithm, (DAlgorithmEngine, PodemEngine, SatAtpg)):
            return algorithm

        if isinstance(algorithm, type) and issubclass(
            algorithm, (DAlgorithmEngine, PodemEngine, SatAtpg)
        ):
            return algorithm(self.circuit)

        if isinstance(algorithm, Stage):
            normalized = algorithm.name.lower()
        else:
            normalized = str(algorithm).lower()
        normalized = normalized.replace("stage.", "").replace(".", "_").replace("-", "_")

        if "d_algo" in normalized or normalized in {"d", "dalgorithm", "d_algorithm"}:
            return DAlgorithmEngine(self.circuit)
        if "podem" in normalized:
            return PodemEngine(self.circuit)
        if normalized.endswith("sat") or "sat" in normalized:
            return SatAtpg(self.circuit)

        raise ValueError(f"Unsupported ATPG algorithm: {algorithm}")
