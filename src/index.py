import argparse
import os
import sys
from time import sleep

from parser import NetlistParseError, parse_netlist


def read_netlist(file_path: str):
    try:
        circuit = parse_netlist(file_path)
        print(f"Successfully parsed netlist from {file_path}")
        print(f"Primary Inputs: {circuit.primary_inputs}")
        print(f"Primary Outputs: {circuit.primary_outputs}")
        print(f"Gates: {list(circuit.gates.keys())}")
        print("")
        sys.stdout.flush()
        return circuit
    except NetlistParseError as e:
        print(f"Error parsing netlist: {e}")
        return None
    

def main(file_path: str):
    circuit = None
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
        
        try:
            user_input = input("Enter a number (0-9): ")
            if user_input == "0":
                print("Reading the input net-list...")
                circuit = read_netlist(file_path)
            elif user_input == "1":
                print("Performing fault collapsing...")
            elif user_input == "2":
                print("Listing fault classes...")
            elif user_input == "3":
                print("Simulating...")
            elif user_input == "4":
                print("Generating tests using D-Algorithm...")
            elif user_input == "5":
                print("Generating tests using PODEM...")
            elif user_input == "6":
                print("Generating tests using Boolean Satisfiability...")
            elif user_input == "7":
                print("Exiting...")
                break
            elif user_input == "8":
                file_path = input("Enter the new file path: ")
                print(f"New file path set to: {file_path}")
                continue
            else:
                print("Invalid input. Please enter a number between 0 and 8.")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        finally:
            if user_input != "7":
                sleep(5)
                os.system("clear")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Automatic Test Generation (ATG) script.")
    parser.add_argument("--file", type=str, required=True, help="Path to the file.")
    return parser.parse_args()


if __name__ == "__main__":

    args = parse_arguments()
    print(f"File path provided: {args.file}")
    main(args.file)
