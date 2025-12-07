 Key 
<gate>-SA-<0|1> - represents a gate with stuck at 1 or 0 fault 

<gate1>--><gate2>-SA-<0|1> -  represents a fanout originating from gate 1 to gate 2 with a stuck at fault 

 

Code Structure 
src/: Main source code directory. 
index.py: The main entry point for application. 
models.py: Contains core data structures needed for ATpG. 
core/: Core logic and algorithms. 
boolean_sat.py, d_algorithm.py, fault_collapsing.py, fault_simulation.py, netlist_parser.py, podem.py: Each file implements a specific algorithm. 
This code contains the main engines for the different parsing, test generation, and simulation algorithms. 
stages/: Interactive handlers for each processing stage. 
collapse.py, d_algorithm.py, parse.py, podem.py, sat.py, simulate.py: Each file handles a stage in the workflow, guiding user interaction or I/O. 
Does not contain logic that solves a task. 
utils/: Utility functions and helpers. 
helpers.py: General-purpose helper functions like a stage manager that describes the state of the system, what dependencies are needed and running stages in order. 
benchmarks/: Contains circuit benchmark files for testing. 
outputs/: Stores output results for each benchmark, organized by circuit and stage. 
README.md: Project overview and instructions. 
 

 

 

Usage Guide 
Install dependencies 
The main dependencies for this project are z3 and z3 solver. These can be resolved by running either of the following code: 

``` 

Pip install z3 z3-solver 

``` 

Or 

``` 

Pip install –r requirements.txt 

``` 

Running the program 
There are 2 key ways to start the project.  

 

Preload benchmark directory with netlists. 
 
In the benchmark directory, add netlists you want to test. 
 
From the main directory run  
```  
Python src/index.py 
``` 
 
Select numbered option from benchmark 
  

Specifying path to file 
 

Simply run 

From the main directory run  
```  
Python src/index.py <path-to-file> 
``` 
 

Main menu 
 
Note: An additional option to use a different netlist was added to allow quick switching between netlists 

Options 0-2 are completely optional. Running any of the choices below will generate the results from earlier stages before proceeding. A subset of the answers may be printed to console, but the entirety of answers are located in the outputs folder. 

For a more detailed explation of how to use this code base: Please watch the following YouTube video: https://youtu.be/i25H0MwtwK0 



 

 

 

 

 

Output Structure 
All stages are logged to an output file. For each circuit that has been loaded, a folder for that circuit will be created.  

Sample Structure 

 

 

For each circuit netlist: 

parse.txt  - stores the parsed I/O and gates. 

Total_faults.out - a list of all faults in the circuit 

Collapsed.txt - shows equivalence and dominance relations 

Note: Dominance collapsing may state that a gate is dominant over a large sum of gates as in the case of 5.10 - agat-SA-0 dominates: egat-SA-1 igat-SA-1 jgat-SA-1 kgat-SA-1 mgat-SA-1.This is just a simplification for a is equivalent to fgat-SA-0(shown in equivalence collapse) which dominates jgat-SA-1 which is equivalent to kgat-SA-1 which is equivalent to egat-SA-1 and mgat-SA-1. It uses equivalence relations to simplify dominance reporting. 

Collapsed_faults.out - The minimalistic list of collapsed faults and their rrepresented classes. 

D_algorithm, podem, sat, simulation folders – store the log file for the results of D Alg, PODEM, Boolean Satisfiability and Simulation respectively. 

 

Results 
For brevity of this report, all outputs have been included in the zipped files in the outputs folder. For each circuit, there is a folder for each circuit with the  