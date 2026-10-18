#!/bin/sh
# Capture successful output; preserve diagnostics and exit status on failure.
silent=false
if [ "${1:-}" = --silent ]; then
    silent=true
    shift
fi

if output="$("$@" 2>&1)"; then
    if [ "$silent" = false ]; then
        echo success
    fi
else
    status=$?
    printf '%s\n' "$output"
    exit "$status"
fi
