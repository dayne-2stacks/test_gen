#!/bin/bash

BENCHMARK_DIR="./benchmarks"

# store parser outputs
OUTPUT_DIR="./outputs"
export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

# Ensure the output dir exists
mkdir -p "$OUTPUT_DIR"

# Iterate over all files in the benchmark directory
for file in "$BENCHMARK_DIR"/*; do
    if [[ -f "$file" ]]; then
        # Extract the filename
        filename=$(basename "$file")
        
        # Run the parser and save the output
        python - "$file" > "$OUTPUT_DIR/${filename}.out" <<'PY'
import sys

from stages.parse import read_netlist

if read_netlist(sys.argv[1]) is None:
    sys.exit(1)
PY
        # Print status
        echo "Processed: $file -> $OUTPUT_DIR/${filename}.out"
    fi
done

echo "All files processed."
