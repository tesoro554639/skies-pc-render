#!/bin/bash
cd "$(dirname "$0")"
FILM="${1:-knocker-upper}"
python3 encode_film.py "films/$FILM"
