#!/bin/bash
set -e

# Change directory to script root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found."
    exit 1
fi

# Run the app
python3 run.py
