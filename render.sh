#!/bin/bash
cd "$(dirname "$0")"
FILM="${1:-knocker-upper}"
python3 run_loop.py "films/$FILM"
