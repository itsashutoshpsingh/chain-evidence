"""Render a recorded terminal session (real command output) as an animated SVG.

Usage: python scripts/term_svg.py session.txt docs/img/demo.svg
session.txt: lines starting with '$ ' are commands (typed), others are output (appear at once).
"""
import html
import sys

W, LH, PAD, COLS = 980, 18, 16, 108
BG, FG, GREEN, AMBER, RED = "#0b0f14", "#c9d1d9", "#00e5a0", "#ffb000", "#ff4d6d"


def colour(line):
    l = line.lower()
    if line.startswith("$ "):
        return GREEN
    if "tampered" in l or "false" in l or "mismatch" in l:
        return RED
    if "ok" in l or "true" in l:
        return FG
    return FG


def main(src, dst):
    lines = []
    for raw in open(src).read().rstrip("\n").split("\n"):
        cmd = raw.startswith("$ ")
        while len(raw) > COLS:
            lines.append(raw[:COLS])
            raw = ("$   " if cmd else "  ") + raw[COLS:]
        lines.append(raw)
    h = PAD * 2 + LH * (len(lines) + 2)
    t, out = 0.4, []
    for i, line in enumerate(lines):
        y = PAD + 28 + i * LH
        txt = html.escape(line)
        if line.startswith("$ "):
            dur = max(0.3, 0.02 * len(line))
            out.append(f'<clipPath id="c{i}"><rect x="{PAD}" y="{y - 14}" height="{LH}" width="0">'
                       f'<animate attributeName="width" from="0" to="{W}" begin="{t:.2f}s" dur="{dur:.2f}s" fill="freeze"/>'
                       f'</rect></clipPath>'
                       f'<text x="{PAD}" y="{y}" fill="{GREEN}" clip-path="url(#c{i})" xml:space="preserve">{txt}</text>')
            t += dur + 0.5
        else:
            out.append(f'<text x="{PAD}" y="{y}" fill="{colour(line)}" opacity="0" xml:space="preserve">{txt}'
                       f'<animate attributeName="opacity" from="0" to="1" begin="{t:.2f}s" dur="0.05s" fill="freeze"/></text>')
            t += 0.06
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
           f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="13">'
           f'<rect width="100%" height="100%" rx="8" fill="{BG}" stroke="#1f2933"/>'
           f'<circle cx="20" cy="16" r="5" fill="{RED}"/><circle cx="36" cy="16" r="5" fill="{AMBER}"/>'
           f'<circle cx="52" cy="16" r="5" fill="{GREEN}"/>'
           f'<text x="{W / 2}" y="20" fill="#6e7681" text-anchor="middle">chain-evidence</text>'
           + "".join(out) + "</svg>")
    open(dst, "w").write(svg)


if __name__ == "__main__":
    main(*sys.argv[1:3])
