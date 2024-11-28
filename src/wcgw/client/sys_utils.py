import subprocess

MAX_RESPONSE_LEN: int = 16000
TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you.</NOTE>"


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN) -> str:
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


def command_run(
    cmd: str,
    timeout: float | None = 3.0,  # seconds
    truncate_after: int | None = MAX_RESPONSE_LEN,
    text: bool = True,
) -> tuple[int, str, str]:
    """Run a shell command synchronously with a timeout."""
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        )
        stdout, stderr = process.communicate(timeout=timeout)
        return (
            process.returncode or 0,
            maybe_truncate(stdout, truncate_after=truncate_after),
            maybe_truncate(stderr, truncate_after=truncate_after),
        )
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise TimeoutError(
            f"Command '{cmd}' timed out after {timeout} seconds"
        ) from exc
