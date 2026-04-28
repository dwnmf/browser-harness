import json, os, sys
from pathlib import Path

# Windows default stdout encoding is cp1252, which can't encode the 🟢 marker
# helpers prepend to tab titles (or anything else outside Latin-1). Force UTF-8
# so `print(page_info())` doesn't UnicodeEncodeError on Windows. Issue #124(4).
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

from .admin import (
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
from . import _ipc as ipc
from .helpers import *

HELP = """Browser Harness

Read SKILL.md for the default workflow and examples.

Typical usage:
  browser-harness -c '
  ensure_real_tab()
  print(page_info())
  '

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
  browser-harness --reload         stop the daemon so next call picks up code changes
"""


def _paths():
    root = Path(__file__).resolve().parent
    repo_root = root.parents[1]
    return {
        "name": os.environ.get("BU_NAME", "default"),
        "endpoint": ipc.sock_addr(os.environ.get("BU_NAME", "default")),
        "log": str(ipc.log_path(os.environ.get("BU_NAME", "default"))),
        "pid": str(ipc.pid_path(os.environ.get("BU_NAME", "default"))),
        "files": {
            "run": str(root / "run.py"),
            "helpers": str(root / "helpers.py"),
            "daemon": str(root / "daemon.py"),
            "admin": str(root / "admin.py"),
            "skill": str(repo_root / "SKILL.md"),
            "install": str(repo_root / "install.md"),
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
    if args and args[0] == "--reload":
        restart_daemon()
        print("daemon stopped — will restart fresh on next call")
        return
    if args and args[0] == "--debug-clicks":
        os.environ["BH_DEBUG_CLICKS"] = "1"
        args = args[1:]
    if args and args[0] == "-c":
        if len(args) < 2:
            sys.exit("Usage: browser-harness -c \"print(page_info())\" or pipe Python on stdin")
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
