"""Nightly: redraw the usage card, commit it if it changed, push.

Run by the Windows scheduled task "kimlj profile usage card" under pythonw, so
nothing it starts may open a window. Everything goes to nightly.log (ignored).
"""

import argparse
import datetime as dt
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_usage_card import NO_WINDOW, ROOT, load, write_cards  # noqa: E402

LOG = ROOT / "nightly.log"
# npm's codeburn 0.9.27 predates #1791 and undercounts parallel tool calls.
# Until a newer release ships, read from a local build of codeburn's main.
LOCAL_CODEBURN = "node C:/Users/kimju/oss-contributions/codeburn-main/dist/cli.js"
LAST_STALE_RELEASE = (0, 9, 27)


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", creationflags=NO_WINDOW,
                         shell=sys.platform == "win32" and cmd[0] == "npm")
    if check and out.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({out.returncode}): "
                           f"{(out.stderr or out.stdout).strip()[:400]}")
    return out


def codeburn_command() -> str:
    try:
        v = run("npm", "view", "codeburn", "version").stdout.strip()
        if tuple(int(p) for p in v.split(".")[:3]) > LAST_STALE_RELEASE:
            return "npx -y codeburn@latest"
    except Exception as e:  # offline or npm missing: the local build still works
        log(f"npm check skipped: {e}")
    return LOCAL_CODEBURN


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    try:
        cmd = codeburn_command()
        write_cards(load(argparse.Namespace(codeburn=cmd, json=None)))
        run("git", "add", "assets")
        if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
            log(f"no change ({cmd})")
            return 0
        run("git", "commit", "-q", "-m", f"Update usage card {dt.date.today()}")
        has_remote = bool(run("git", "remote").stdout.strip())
        pushed = not args.no_push and has_remote
        if pushed:
            run("git", "push", "-q")
        why = "" if pushed else (" (no remote yet)" if not has_remote else " (not pushed)")
        log(f"updated{' and pushed' if pushed else why} ({cmd})")
        return 0
    except Exception:
        log("FAILED\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
