import subprocess

from fitness.contracts import FitnessError


def execute_process(command: list[str], stdin: str | None) -> str:
    try:
        result = subprocess.run(
            command,
            input=stdin,
            stdin=subprocess.DEVNULL if stdin is None else None,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FitnessError(str(error)) from error
    if result.returncode:
        raise FitnessError(f"exit {result.returncode}: {result.stderr.strip()}")
    return result.stdout
