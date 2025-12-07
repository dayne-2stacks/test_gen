import os
import sys

from stages import (
    perform_fault_collapsing,
    read_netlist,
    run_boolean_satisfiability,
    run_d_algorithm,
    run_fault_simulation,
    run_podem,
)
from utils import Stage, StageManager

import argparse

# Extract CLI arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description="Automatic Test Generation (ATG) script.")
    parser.add_argument("--file", type=str, required=True, help="Path to the file.")
    return parser.parse_args()


def main(file_path: str):
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
        
        user_input = ""
        try:
            user_input = input("Enter a number (0-9): ")
            rerun_stage = {
                "0": Stage.PARSE,
                "1": Stage.COLLAPSE,
                "3": Stage.SIMULATE,
                "4": Stage.D_ALGO,
                "5": Stage.PODEM,
                "6": Stage.SAT,
            }.get(user_input)
            if user_input == "0":
                print("Reading the input net-list...")
                stage_manager.ensure(Stage.PARSE, force=rerun_stage == Stage.PARSE)
            elif user_input == "1":
                stage_manager.ensure(Stage.COLLAPSE, force=rerun_stage == Stage.COLLAPSE)
            elif user_input == "2":
                stage_manager.ensure(Stage.COLLAPSE, force=rerun_stage == Stage.COLLAPSE)
                collapse_result = stage_manager.collapse_result
                if collapse_result is not None:
                    print("Collapsed fault classes:")
                    for fault_class in collapse_result.classes:
                        members = ", ".join(str(f) for f in sorted(fault_class.members, key=lambda f: (f.net, f.stuck_at)))
                        print(f"  {fault_class.representative}: {members}")
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
                file_path = input("Enter the new file path: ")
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


if __name__ == "__main__":

    args = parse_arguments()
    print(f"File path provided: {args.file}")
    main(args.file)
