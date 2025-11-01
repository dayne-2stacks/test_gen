#!/bin/bash

BENCHMARK_DIR="./benchmarks"

# store parser outputs
OUTPUT_DIR="./outputs"

# Ensure the output dir exists
mkdir -p "$OUTPUT_DIR"

# Iterate over all files in the benchmark directory
for file in "$BENCHMARK_DIR"/*; do
    if [[ -f "$file" ]]; then
        # Extract the filename
        filename=$(basename "$file")
        
        # Run the parser and save the output
        python src/parser.py "$file" > "$OUTPUT_DIR/${filename}.out"
        # Print status
        echo "Processed: $file -> $OUTPUT_DIR/${filename}.out"
    fi
done

echo "All files processed."