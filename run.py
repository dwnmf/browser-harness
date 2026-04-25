import json, os, socket, sys, tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from admin import (
    _version,
    ensure_daemon,
    list_cloud_profiles,
    list_local_profiles,
    print_update_banner,
    restart_daemon,
    run_doctor,
    run_setup,
    run_update,
    start_remote_daemon,
    stop_remote_daemon,
    sync_local_profile,
)
from helpers import *

NAME = os.environ.get("BU_NAME", "default")

HELP = """Browser Harness

Read SKILL.md for the default workflow and examples.

Typical usage:
  browser-harness -c "ensure_real_tab(); print(page_info())"

PowerShell stdin:
  @'
  ensure_real_tab()
  print(page_info())
  '@ | browser-harness

Bash/zsh stdin:
  browser-harness <<'PY'
  ensure_real_tab()
  print(page_info())
  PY

Helpers are pre-imported. The daemon auto-starts and connects to the running browser.

Commands:
  browser-harness --version        print the installed version
  browser-harness --doctor         diagnose install, daemon, and browser state
  browser-harness --paths          print editable harness files and daemon endpoint
  browser-harness --setup          interactively attach to your running browser
  browser-harness --update [-y]    pull the latest version (agents: pass -y)
"""


def _paths():
    root = Path(__file__).resolve().parent
    tmp = Path(tempfile.gettempdir())
    supports_unix = hasattr(socket, "AF_UNIX")
    port = int(os.environ.get("BU_PORT", 39300 + (sum(ord(c) for c in NAME) % 1000)))
    return {
        "name": NAME,
        "endpoint": f"/tmp/bu-{NAME}.sock" if supports_unix else f"127.0.0.1:{port}",
        "log": str(tmp / f"bu-{NAME}.log"),
        "pid": str(tmp / f"bu-{NAME}.pid"),
        "files": {
            "run": str(root / "run.py"),
            "helpers": str(root / "helpers.py"),
            "daemon": str(root / "daemon.py"),
            "admin": str(root / "admin.py"),
            "skill": str(root / "SKILL.md"),
            "install": str(root / "install.md"),
        },
    }


def main():
    args = sys.argv[1:]
    if args and args[0] in {"-h", "--help"}:
        print(HELP)
        return
    if args and args[0] == "--version":
        print(_version() or "unknown")
        return
    if args and args[0] == "--doctor":
        sys.exit(run_doctor())
    if args and args[0] == "--paths":
        print(json.dumps(_paths(), ensure_ascii=False, indent=2))
        return
    if args and args[0] == "--setup":
        sys.exit(run_setup())
    if args and args[0] == "--update":
        yes = any(a in {"-y", "--yes"} for a in args[1:])
        sys.exit(run_update(yes=yes))
    if args and args[0] == "--debug-clicks":
        os.environ["BH_DEBUG_CLICKS"] = "1"
        args = args[1:]
    if args and args[0] == "-c":
        code = args[1]
    elif not args and not sys.stdin.isatty():
        code = sys.stdin.read()
    else:
        sys.exit("Usage: browser-harness -c \"print(page_info())\" or pipe Python on stdin")
    print_update_banner()
    ensure_daemon()
    exec(code, globals())


if __name__ == "__main__":
    main()
