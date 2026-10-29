"""Render this month's codeburn usage as two SVG cards (light and dark).

codeburn reads local session files, so this runs on Kim's machine, not in
GitHub Actions. Usage:

    python scripts/update_usage_card.py                 # runs `npx -y codeburn`
    python scripts/update_usage_card.py --codeburn "node C:/path/to/dist/cli.js"
    python scripts/update_usage_card.py --json month.json   # render a saved export
"""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent

# kimlj.dev's own tokens, so the card matches the site.
THEMES = {
    "light": {"bg": "#ffffff", "border": "#e4e4e0", "text": "#18181b",
              "muted": "#6b6b66", "accent": "#0891b2", "track": "#f0f0ee"},
    "dark": {"bg": "#111113", "border": "#27272a", "text": "#f4f4f5",
             "muted": "#8a8a93", "accent": "#c8ff00", "track": "#1c1c1f"},
}
MONO = "ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace"
W, PAD = 780, 28
# The nightly task runs under pythonw; without this every child opens a console.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load(args) -> dict:
    if args.json:
        return json.loads(Path(args.json).read_text(encoding="utf-8"))
    cmd = shlex.split(args.codeburn, posix=False) + ["month", "--format", "json"]
    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         shell=sys.platform == "win32", creationflags=NO_WINDOW)
    if run.returncode != 0:
        sys.exit(f"codeburn failed ({run.returncode}): {run.stderr.strip()[:400]}")
    return json.loads(run.stdout)


def short(n: float) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= size:
            return f"{n / size:.2f}{unit}" if unit == "B" else f"{n / size:.1f}{unit}"
    return f"{n:,.0f}"


def text(x, y, s, fill, size=13, weight=400, anchor="start"):
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(s))}</text>')


def card(d: dict, t: dict) -> str:
    o = d["overview"]
    tok = o["tokens"]
    total_tokens = tok["input"] + tok["output"] + tok["cacheRead"] + tok["cacheWrite"]
    stats = [
        ("sessions", f"{o['sessions']:,}"),
        ("model calls", f"{o['calls']:,}"),
        ("tokens", short(total_tokens)),
        ("cache hit", f"{o['cacheHitPercent']}%"),
    ]

    # Share of model calls: top four by calls, the rest folded into "other".
    models = sorted(d["models"], key=lambda m: m["calls"], reverse=True)
    calls = sum(m["calls"] for m in models) or 1
    shares = [(m["name"], m["calls"]) for m in models[:4]]
    rest = calls - sum(c for _, c in shares)
    if rest > 0:
        shares.append(("other", rest))

    tools = sorted(d["tools"], key=lambda x: x["calls"], reverse=True)[:6]

    out, y = [], 44
    out.append(text(PAD, y, f"codeburn  {d['period']}", t["text"], 15, 700))
    out.append(text(W - PAD, y, f"${o['cost']:,.0f} at API list prices", t["muted"], 12,
                    anchor="end"))

    y += 40
    col = (W - 2 * PAD) / len(stats)
    for i, (label, value) in enumerate(stats):
        x = PAD + i * col
        out.append(text(x, y, value, t["accent"], 24, 700))
        out.append(text(x, y + 20, label, t["muted"], 12))

    y += 54
    out.append(text(PAD, y, "share of model calls", t["muted"], 12))
    y += 14
    bar_w, x = W - 2 * PAD, PAD
    out.append(f'<rect x="{PAD}" y="{y}" width="{bar_w}" height="10" rx="5" fill="{t["track"]}"/>')
    opacities = [1, 0.7, 0.5, 0.35, 0.2]
    for i, (_, c) in enumerate(shares):
        w = bar_w * c / calls
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="10" '
                   f'fill="{t["accent"]}" fill-opacity="{opacities[i]}"/>')
        x += w
    y += 30
    x = PAD
    for i, (name, c) in enumerate(shares):
        label = f"{name} {100 * c / calls:.0f}%"
        out.append(f'<rect x="{x}" y="{y - 9}" width="9" height="9" rx="2" '
                   f'fill="{t["accent"]}" fill-opacity="{opacities[i]}"/>')
        out.append(text(x + 15, y, label, t["text"], 12))
        x += 15 + len(label) * 7.4 + 18

    y += 34
    out.append(text(PAD, y, "top tools", t["muted"], 12))
    y += 22
    col = (W - 2 * PAD) / 3
    for i, tool in enumerate(tools):
        cx, cy = PAD + (i % 3) * col, y + (i // 3) * 22
        out.append(text(cx, cy, tool["name"], t["text"], 13))
        out.append(text(cx + col - 24, cy, f"{tool['calls']:,}", t["muted"], 13, anchor="end"))

    h = y + 22 * ((len(tools) + 2) // 3) + 14
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" '
            f'viewBox="0 0 {W} {h}" font-family="{MONO}" role="img" '
            f'aria-label="codeburn usage for {escape(d["period"])}">'
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="12" '
            f'fill="{t["bg"]}" stroke="{t["border"]}"/>' + "".join(out) + "</svg>\n")


def write_cards(data: dict) -> None:
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        path = assets / f"usage-{name}.svg"
        path.write_text(card(data, theme), encoding="utf-8")
        if sys.stdout:  # None under pythonw
            print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codeburn", default="npx -y codeburn")
    ap.add_argument("--json")
    write_cards(load(ap.parse_args()))


if __name__ == "__main__":
    main()
