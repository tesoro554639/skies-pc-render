#!/bin/bash
cd "$(dirname "$0")"
FILM="${1:-knocker-upper}"
shift 2>/dev/null || true
python3 encode_film.py "films/$FILM" "$@"
