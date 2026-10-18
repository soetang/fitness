#!/usr/bin/env bash
# Run commands separated by :::, stopping at the first failure.
run_command() {
    if [ "$#" -eq 0 ]; then
        echo 'quiet: expected a command' >&2
        exit 2
    fi
    local output status
    if output="$("$@" 2>&1)"; then
        return 0
    else
        status=$?
        printf '%s\n' "$output" >&2
        exit "$status"
    fi
}

command=()
for argument in "$@"; do
    if [ "$argument" = ::: ]; then
        run_command "${command[@]}"
        command=()
    else
        command+=("$argument")
    fi
done
run_command "${command[@]}"
echo success
