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
    - [0] Read the input net-list
    - [1] Perform fault collapsing
    - [2] List fault classes
    - [3] Simulate
    - [4] Generate tests (D-Algorithm)
    - [5] Generate tests (PODEM)
    - [6] Generate tests (Boolean Satisfaibility)
    - [7] Exit


## Directory Structure

```
src/
├── stages/         # Contains modular stage handlers for parsing, collapsing, simulation, and test generation.
├── core/          # Core engines for parsing, fault simulation, and collapsing, designed to be I/O agnostic.
├── utils/          # Utility functions and helpers for shared operations across modules.
├── models.py       # Data models and abstractions for representing circuits and faults.
├── cli.py          # Command-line interface logic for handling user inputs and menu interactions.
└── index.py         # Entry point for the interactive program.
```


## Usage

Install Requirements
```
pip install -r requirements.txt
```

run code
```
python src/index.py --file [netlist_path]
```

### Stage workflow
- Parse (`[0] Read the input net-list`): runs `stages.parse.read_netlist` through `StageManager.ensure`, prints primary inputs/outputs and writes a parse summary to `outputs/<netlist>/parse.txt`.
- Fault collapsing (`[1] Perform fault collapsing`): uses `stages.collapse.perform_fault_collapsing` to create collapsed/dominated sets, saving `total_faults.out` and `collapsed_faults.out` under `outputs/<netlist>/`.
- List fault classes (`[2] List fault classes`): relies on the prior collapse stage and prints each collapsed class from `StageManager.collapse_result`.
- Simulate (`[3] Simulate`): `stages.simulate.run_fault_simulation` prompts for scope, presence mode, bit-parallel vs serial, and an input vector; results are summarized in the console and written to `outputs/<netlist>/simulation/`.
- Generate tests (D-Algorithm/PODEM/SAT) (`[4]`, `[5]`, `[6]`): each option routes through the corresponding stage module and `AtpgEngine` with manual (choose faults) or automatic (all collapsed faults) modes; generated vectors and detection summaries are written to `outputs/<netlist>/{d_algorithm|podem|sat}/test_vectors.out`. Each stage will automatically trigger required prerequisites via `StageManager.ensure`.
