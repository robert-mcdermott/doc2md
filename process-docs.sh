#!/bin/bash

# Define the input directory and output directory
input_dir="intake"
output_dir="output"

# Create the output directory if it doesn't exist
mkdir -p "$output_dir"

# Iterate over all PDF files in the intake directory
for pdf_file in "$input_dir"/*.pdf; do
  # Check if there are any PDF files
  if [ ! -e "$pdf_file" ]; then
    echo "No PDF files found in $input_dir."
    exit 1
  fi

  # Extract the filename without extension
  filename=$(basename "$pdf_file" .pdf)

  # Construct the output markdown file path
  output_file="$output_dir/$filename.md"

  # Execute the command
  uv run doc2md.py -c config.toml -o "$output_file" "$pdf_file"
  
  # Optional: Print a message indicating the conversion was successful
  echo "Converted $pdf_file to $output_file"
done
