import os
import sys

# Import stage handlers for each ATG processing step
from stages import (
    perform_fault_collapsing,  # Fault collapsing stage
    read_netlist,              # Netlist parsing stage
    run_boolean_satisfiability,# SAT-based test generation
    run_d_algorithm,           # D-Algorithm test generation
    run_fault_simulation,      # Fault simulation stage
    run_podem,                 # PODEM test generation
)
from utils import Stage, StageManager

import argparse

# Extract CLI arguments for the ATG tool
def parse_arguments():
    """
    Parse command-line arguments for the ATG script.
    """
    parser = argparse.ArgumentParser(description="Automatic Test Generation (ATG) script.")
    parser.add_argument("--file", type=str, required=True, help="Path to the file.")
    return parser.parse_args()


def main(file_path: str):
    """
    Main entrypoint for the ATG CLI. Initializes the stage manager and presents the user menu.
    """
    # Initialize the stage manager with handlers for each stage
    stage_manager = StageManager(
        file_path,
        {
            Stage.PARSE: read_netlist,
            Stage.COLLAPSE: perform_fault_collapsing,
            Stage.SIMULATE: run_fault_simulation,
            Stage.D_ALGO: run_d_algorithm,
            Stage.PODEM: run_podem,
            Stage.SAT: run_boolean_satisfiability,
        },
    )
    # Main interactive loop for user input
    while True:
        print(" Welcome to Automatic Test Generation (ATG) by Dayne Guy and Lazar Lazarevic. ")
        print(" Please select one of the following options (<0-8>): ") 
        print("""
        [0] Read the input net-list
        [1] Perform fault collapsing
        [2] List fault classes
        [3] Simulate
        [4] Generate tests (D-Algorithm)
        [5] Generate tests (PODEM)
        [6] Generate tests (Boolean Satisfiability)
        [7] Exit
        [8] Use a different input file
        """)
        # Get user input and map to stage
        user_input = ""
        try:
            user_input = input("Enter a number (0-8): ")
            # Map menu to stage
            rerun_stage = {
                "0": Stage.PARSE,
                "1": Stage.COLLAPSE,
                "3": Stage.SIMULATE,
                "4": Stage.D_ALGO,
                "5": Stage.PODEM,
                "6": Stage.SAT,
            }.get(user_input)
            # Based on input, run correct stage
            if user_input == "0":
                print("Reading the input net-list...")
                stage_manager.ensure(Stage.PARSE, force=rerun_stage == Stage.PARSE)
            elif user_input == "1":
                stage_manager.ensure(Stage.COLLAPSE, force=rerun_stage == Stage.COLLAPSE)
            elif user_input == "2":
                stage_manager.ensure(Stage.COLLAPSE, force=rerun_stage == Stage.COLLAPSE)
                collapse_result = stage_manager.collapse_result
                if collapse_result is not None:
                    print("Equivalent fault classes removed:")
                    dominated_map = collapse_result.dominated_faults
                    fault_to_rep = collapse_result.fault_to_representative
                    grouped = {rep: [] for rep in collapse_result.collapsed_faults}

                    for fault, rep in fault_to_rep.items():
                        while rep in dominated_map:
                            rep = dominated_map[rep]
                        grouped.setdefault(rep, []).append(fault)

                    for representative in sorted(
                        grouped, key=lambda f: (f.net, f.sink or "", f.stuck_at)
                    ):
                        members = " ".join(
                            str(fault)
                            for fault in sorted(
                                grouped[representative],
                                key=lambda f: (f.net, f.sink or "", f.stuck_at),
                            )
                        )
                        print(f"  {representative}: {members}")
                else:
                    print("Unable to list fault classes without a successful fault collapsing run.")
            elif user_input == "3":
                stage_manager.ensure(Stage.SIMULATE, force=rerun_stage == Stage.SIMULATE)
            elif user_input == "4":
                print("Generating tests using D-Algorithm...")
                stage_manager.ensure(Stage.D_ALGO, force=rerun_stage == Stage.D_ALGO)
            elif user_input == "5":
                print("Generating tests using PODEM...")
                stage_manager.ensure(Stage.PODEM, force=rerun_stage == Stage.PODEM)
            elif user_input == "6":
                print("Generating tests using Boolean Satisfiability...")
                stage_manager.ensure(Stage.SAT, force=rerun_stage == Stage.SAT)
            elif user_input == "7":
                print("Exiting...")
                break
            elif user_input == "8":
                new_path = input("Enter the new file path: ").strip()
                file_path = new_path if os.path.isfile(new_path) else resolve_input_file(new_path)
                stage_manager.set_file_path(file_path)
                print(f"New file path set to: {file_path}")
                continue
            else:
                print("Invalid input. Please enter a number between 0 and 8.")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        finally:
            if user_input != "7":
                sys.stdout.flush()
                try:
                    input("Press Enter to continue...")
                except EOFError:
                    pass
                os.system('clear')


def resolve_input_file(initial_path: str) -> str:
    file_path = initial_path
    benchmarks_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
    benchmark_files = []
    if os.path.isdir(benchmarks_dir):
        for entry in sorted(os.listdir(benchmarks_dir)):
            candidate = os.path.join(benchmarks_dir, entry)
            if os.path.isfile(candidate):
                benchmark_files.append(candidate)

    while not os.path.isfile(file_path):
        print(f"File '{file_path}' does not exist.")
        if benchmark_files:
            print("Select a benchmark file:")
            for idx, benchmark in enumerate(benchmark_files, 1):
                rel_path = os.path.relpath(benchmark, os.getcwd())
                print(f"  [{idx}] {rel_path}")
        user_choice = input("Enter a valid file path or choose a benchmark number: ").strip()
        if user_choice.isdigit():
            candidate_idx = int(user_choice) - 1
            if 0 <= candidate_idx < len(benchmark_files):
                file_path = benchmark_files[candidate_idx]
                continue
        if user_choice:
            file_path = user_choice
    print(f"Using file: {file_path}")
    return file_path


if __name__ == "__main__":

    args = parse_arguments()
    print(f"File path provided: {args.file}")
    file_path = args.file if os.path.isfile(args.file) else resolve_input_file(args.file)
    main(file_path)
    
