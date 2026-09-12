import re
from pathlib import Path

from wcgw.client.bash_state.bash_state import (
    PROMPT_CONST,
    ensure_wcgw_block_in_rc_file,
    generate_thread_id,
    start_shell,
)
from wcgw.types_ import Console


class RecordingConsole(Console):
    def __init__(self) -> None:
        self.logs: list[str] = []
        self.prints: list[str] = []

    def log(self, msg: str) -> None:
        self.logs.append(msg)

    def print(self, msg: str) -> None:
        self.prints.append(msg)


def test_fallback_shell_preserves_initial_directory(tmp_path: Path) -> None:
    shell, _ = start_shell(
        False,
        str(tmp_path),
        RecordingConsole(),
        False,
        "/definitely/not-a-shell",
    )
    try:
        shell.sendline("pwd")
        shell.expect(re.escape(str(tmp_path)), timeout=3)
        shell.expect(PROMPT_CONST, timeout=3)
    finally:
        shell.close(force=True)


def test_zsh_block_upgrades_existing_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text(
        "before\n"
        "# --WCGW_ENVIRONMENT_START--\n"
        "if [ -n \"$IN_WCGW_ENVIRONMENT\" ]; then\n"
        " old-wcgw-hook\n"
        "fi\n"
        "# --WCGW_ENVIRONMENT_END--\n"
        "after\n"
    )

    ensure_wcgw_block_in_rc_file("/usr/bin/zsh", RecordingConsole())

    content = zshrc.read_text()
    assert "before\n" in content
    assert "after\n" in content
    assert "old-wcgw-hook" not in content
    assert "autoload -Uz add-zsh-hook" in content
    assert "add-zsh-hook -d precmd prmptcmdwcgw" in content
    assert "add-zsh-hook precmd prmptcmdwcgw" in content


def test_generated_thread_id_has_collision_resistant_shape() -> None:
    assert re.fullmatch(r"i[0-9a-f]{32}", generate_thread_id()) is not None
