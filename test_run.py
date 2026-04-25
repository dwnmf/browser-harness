import sys
import json
from io import StringIO
from unittest.mock import patch
import run


def test_c_flag_executes_code():
    stdout = StringIO()
    with patch.object(sys, "argv", ["browser-harness", "-c", "print('hello from -c')"]), \
         patch("run.ensure_daemon"), \
         patch("run.print_update_banner"), \
         patch("sys.stdout", stdout):
        run.main()
    assert stdout.getvalue().strip() == "hello from -c"


def test_c_flag_does_not_read_stdin():
    stdin_read = []
    fake_stdin = StringIO("should not be read")
    fake_stdin.read = lambda: stdin_read.append(True) or ""

    with patch.object(sys, "argv", ["browser-harness", "-c", "x = 1"]), \
         patch("run.ensure_daemon"), \
         patch("run.print_update_banner"), \
         patch("sys.stdin", fake_stdin):
        run.main()

    assert not stdin_read, "stdin should not be read when -c is passed"


def test_paths_prints_editable_files_without_daemon():
    stdout = StringIO()
    with patch.object(sys, "argv", ["browser-harness", "--paths"]), \
         patch("sys.stdout", stdout), \
         patch("run.ensure_daemon") as ensure_daemon:
        run.main()

    payload = json.loads(stdout.getvalue())
    assert payload["files"]["helpers"].endswith("helpers.py")
    assert payload["files"]["skill"].endswith("SKILL.md")
    assert "endpoint" in payload
    ensure_daemon.assert_not_called()
