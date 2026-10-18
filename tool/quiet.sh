#!/bin/sh
# Capture successful output; preserve diagnostics and exit status on failure.
if output="$("$@" 2>&1)"; then
    :
else
    status=$?
    printf '%s\n' "$output"
    exit "$status"
fi
