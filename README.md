# Test Generator for VLSI Circuits
This project is the implementation of an Automatic Test Generator (ATG) for single stuck-at faults done by: Dayne Guy and Lazar Lazarevic

This test generator produces test vectors and by default performs:

## Fault Collapsing 
Removes equivalent single stuck-at faults and faults that are dominated by another fault.

## Circuit Simulation 
Need to decide on which simulation mode we will use

## Test Generation
and generation using D-Algorithm, PODEM and Boolean Satisfiability

Key Features
1. The program runs in an interactive mode.
2. The input to the program is a gate-level net-list.
3. The generator parses the gate-level netlist and then report the following:
    - The final list of fault classes after performing fault collapsing
    - For each detectable fault, show the list of test vectors that will detect such faults.
    - The list of undetectable faults (if any).
    - The list of detectable faults for a given test vector revealed by circuit simulation.


On program invocation, the following interactive menu below is presented to the user:
                    [0] Read the input net-list
                    [1] Perform fault collapsing
                    [2] List fault classes
                    [3] Simulate
                    [4] Generate tests (D-Algorithm)
                    [5] Generate tests (PODEM)
                    [6] Generate tests (Boolean Satisfaibility)
                    [7] Exit
