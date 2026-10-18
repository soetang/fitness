#!/bin/sh
# Capture successful output; preserve diagnostics and exit status on failure.
if output="$("$@" 2>&1)"; then
    if [ "${FITNESS_QUIET_SUCCESS:-0}" != 1 ]; then
        echo success
    fi
else
    status=$?
    printf '%s\n' "$output"
    exit "$status"
fi
