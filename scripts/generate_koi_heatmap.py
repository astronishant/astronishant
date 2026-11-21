#!/usr/bin/env python3
"""
Generate a koi-pond contribution heatmap SVG for a GitHub profile README.

The SVG is a normal image, so it animates on GitHub (inline <svg> is stripped
from READMEs). A GitHub Action runs this daily and commits the refreshed file.

Usage:
    python scripts/generate_koi_heatmap.py --user astronishant --out assets/koi-heatmap.svg
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import urllib.request
from pathlib import Path

# ── pond palette (matches the README theme) ───────────────────────────────────
LEVEL_COLORS = {
    0: "#0d1f2d",
    1: "#0a3d3d",
    2: "#0e6655",
    3: "#1aa36a",
    4: "#26d47a",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

USER_AGENT = "koi-heatmap/1.0 (+https://github.com/{user})"

# (shape id, scale, swims_left, duration seconds, start offset seconds)
LANE_FISH = [
    ("koiO", 0.72, False, 13, 0.0),
    ("koiG", 0.64, True, 17, 2.5),
    ("koiW", 0.68, False, 15, 5.0),
    ("koiB", 0.58, True, 11, 1.5),
    ("koiO", 0.56, True, 12, 7.0),
    ("koiG", 0.62, False, 16, 3.5),
    ("koiW", 0.52, False, 18, 9.0),
    ("koiB", 0.50, True, 10, 6.0),
]

# a few extra koi so no two lanes ever feel empty
EXTRA_FISH = [
    (0, "koiW", 0.55, True, 14, 6.0),
    (2, "koiB", 0.50, False, 12, 2.0),
    (4, "koiG", 0.50, True, 19, 8.0),
    (6, "koiO", 0.48, False, 11, 4.0),
]


# ── data fetching ─────────────────────────────────────────────────────────────

def fetch_html(user: str) -> str:
    url = f"https://github.com/users/{user}/contributions"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT.format(user=user),
            "Accept-Language": "en",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as res:
        return res.read().decode("utf-8", "replace")


def parse_days(html: str) -> list[dict]:
    """Parse the contribution calendar HTML into [{date, level, count}, ...]."""
    # tooltip id -> contribution count
    counts: dict[str, int] = {}
    for tip_id, body in re.findall(
        r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>(.*?)</tool-tip>',
        html,
        flags=re.I | re.S,
    ):
        text = re.sub(r"<[^>]+>", " ", body)
        m = re.search(r"([\d,]+)\s+contribution", text)
        counts[tip_id] = int(m.group(1).replace(",", "")) if m else 0

    days: dict[str, dict] = {}
    for tag in re.findall(r"<td\b[^>]*>", html, flags=re.I):
        dm = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        if not dm:
            continue
        lm = re.search(r'data-level="(\d)"', tag)
        im = re.search(r'\bid="([^"]+)"', tag)
        date = dm.group(1)
        days[date] = {
            "date": date,
            "level": int(lm.group(1)) if lm else 0,
            "count": counts.get(im.group(1), 0) if im else 0,
        }

    # older GitHub markup used <rect data-date data-count>
    if not days:
        for tag in re.findall(r"<rect\b[^>]*>", html, flags=re.I):
            dm = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
            if not dm:
                continue
            cm = re.search(r'data-count="(\d+)"', tag)
            count = int(cm.group(1)) if cm else 0
            level = 0 if count == 0 else 1 if count < 4 else 2 if count < 8 else 3 if count < 12 else 4
            days[dm.group(1)] = {"date": dm.group(1), "level": level, "count": count}

    return sorted(days.values(), key=lambda d: d["date"])


# ── geometry / stats ──────────────────────────────────────────────────────────

def build_weeks(days: list[dict]) -> list[list[dict]]:
    """Group days into Sunday-to-Saturday columns."""
    by_date = {d["date"]: d for d in days}
    first = dt.date.fromisoformat(days[0]["date"])
    last = dt.date.fromisoformat(days[-1]["date"])
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # back to Sunday

    weeks: list[list[dict]] = []
    cursor = start
    while cursor <= last:
        week = []
        for i in range(7):
            day = cursor + dt.timedelta(days=i)
            iso = day.isoformat()
            entry = by_date.get(iso)
            if entry is None:
                entry = {"date": iso, "level": 0, "count": 0, "outside": True}
            week.append(entry)
        weeks.append(week)
        cursor += dt.timedelta(days=7)
    return weeks


def current_streak(days: list[dict]) -> int:
    by_date = {d["date"]: d["count"] for d in days}
    cursor = dt.date.fromisoformat(days[-1]["date"])
    if by_date.get(cursor.isoformat(), 0) == 0:
        cursor -= dt.timedelta(days=1)
    streak = 0
    while by_date.get(cursor.isoformat(), 0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak


# ── SVG rendering ─────────────────────────────────────────────────────────────

FISH_DEFS = """
    <linearGradient id="fgO" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#ff8c38"/><stop offset="60%" stop-color="#ff4500"/><stop offset="100%" stop-color="#b83000"/>
    </linearGradient>
    <linearGradient id="fgG" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#ffe44a"/><stop offset="55%" stop-color="#ffaa00"/><stop offset="100%" stop-color="#cc7700"/>
    </linearGradient>
    <linearGradient id="fgW" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f0ebe3"/><stop offset="60%" stop-color="#d8d0c4"/><stop offset="100%" stop-color="#b0a898"/>
    </linearGradient>
    <linearGradient id="fgBk" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#3a4a58"/><stop offset="60%" stop-color="#141c24"/>
    </linearGradient>

    <g id="koiO">
      <ellipse cx="0" cy="0" rx="13" ry="4.5" fill="url(#fgO)"/>
      <ellipse cx="2" cy="1.2" rx="8" ry="2.2" fill="#ff6600" opacity="0.35"/>
      <path d="M -4,-4.5 Q 1,-10 6,-4.5" fill="#ff6600" opacity="0.75"/>
      <path d="M -13,0 L -19,-6 L -19,6 Z" fill="#ff6600" opacity="0.85"/>
      <path d="M 3,2.5 Q 7,8 1.5,7" fill="#ff6600" opacity="0.6"/>
      <circle cx="10" cy="-1.2" r="1.6" fill="#0a0a0a"/>
      <circle cx="10.5" cy="-1.7" r="0.5" fill="#ffffff"/>
    </g>

    <g id="koiW">
      <ellipse cx="0" cy="0" rx="13" ry="4.5" fill="url(#fgW)"/>
      <ellipse cx="-3" cy="-1.2" rx="4" ry="2.8" fill="#ff5500" opacity="0.7"/>
      <ellipse cx="5" cy="1.4" rx="3.5" ry="2" fill="#ff3300" opacity="0.55"/>
      <path d="M -4,-4.5 Q 1,-10 6,-4.5" fill="#c8c0b4" opacity="0.8"/>
      <path d="M -13,0 L -19,-6 L -19,6 Z" fill="#c8c0b4" opacity="0.9"/>
      <circle cx="10" cy="-1.2" r="1.5" fill="#111111"/>
      <circle cx="10.4" cy="-1.6" r="0.5" fill="#ffffff"/>
    </g>

    <g id="koiG">
      <ellipse cx="0" cy="0" rx="12" ry="4.2" fill="url(#fgG)"/>
      <ellipse cx="1.5" cy="1.2" rx="7" ry="2" fill="#ffe97a" opacity="0.4"/>
      <path d="M -3.5,-4.2 Q 1,-9.5 5.5,-4.2" fill="#ddaa00" opacity="0.8"/>
      <path d="M -12,0 L -17.5,-5.5 L -17.5,5.5 Z" fill="#cc8800" opacity="0.9"/>
      <circle cx="9" cy="-1.1" r="1.3" fill="#111111"/>
      <circle cx="9.4" cy="-1.5" r="0.45" fill="#ffffff"/>
    </g>

    <g id="koiB">
      <ellipse cx="0" cy="0" rx="11" ry="3.8" fill="url(#fgBk)"/>
      <ellipse cx="2.5" cy="-0.9" rx="3.2" ry="2.2" fill="#9fb0bd" opacity="0.35"/>
      <path d="M -3.2,-3.8 Q 0.8,-8.4 4.5,-3.8" fill="#1a2430" opacity="0.9"/>
      <path d="M -11,0 L -15.5,-5 L -15.5,5 Z" fill="#1a2430" opacity="0.95"/>
      <circle cx="8.5" cy="-1.1" r="1.2" fill="#ff3300"/>
      <circle cx="8.9" cy="-1.5" r="0.4" fill="#ffffff"/>
    </g>
"""


def fish_markup(shape: str, scale: float, swims_left: bool, dur: int, phase: float, lane_y: float) -> str:
    if swims_left:
        start_x, end_x = 900, -40
        scale_attr = f"scale(-{scale},{scale})"
        wobble = (-1.2, 1.0, -0.6)
    else:
        start_x, end_x = -40, 900
        scale_attr = f"scale({scale})"
        wobble = (1.2, -1.0, 0.6)

    path = (f"M {start_x},{lane_y + wobble[0]:.1f} "
            f"Q 430,{lane_y + wobble[1]:.1f} {end_x},{lane_y + wobble[2]:.1f}")

    return (
        f'    <g>\n'
        f'      <animateMotion dur="{dur}s" begin="-{phase:.1f}s" repeatCount="indefinite" '
        f'rotate="0" path="{path}"/>\n'
        f'      <use href="#{shape}" transform="{scale_attr}"/>\n'
        f'    </g>\n'
    )


def render_svg(days: list[dict], weeks: list[list[dict]], user: str) -> str:
    width, height = 860, 158
    cell, gap, pitch = 11, 3, 14
    grid_top = 30
    grid_width = len(weeks) * pitch - gap
    grid_x = round((width - grid_width) / 2)

    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"] > 0)
    peak = max((d["count"] for d in days), default=0)
    streak = current_streak(days)

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="{user} koi pond contribution heatmap">\n'
    )
    out.append(f'  <title>{user} — {total:,} contributions in the last year</title>\n')
    out.append('  <defs>\n')
    out.append(
        '    <radialGradient id="sheen" cx="50%" cy="50%" r="50%">\n'
        '      <stop offset="0%" stop-color="#38b2d8" stop-opacity="0.07"/>\n'
        '      <stop offset="100%" stop-color="#38b2d8" stop-opacity="0"/>\n'
        '    </radialGradient>\n'
        '    <radialGradient id="sheen2" cx="50%" cy="50%" r="50%">\n'
        '      <stop offset="0%" stop-color="#1a6b8a" stop-opacity="0.08"/>\n'
        '      <stop offset="100%" stop-color="#1a6b8a" stop-opacity="0"/>\n'
        '    </radialGradient>\n'
        f'    <clipPath id="pondClip"><rect width="{width}" height="{height}" rx="12"/></clipPath>\n'
    )
    out.append(FISH_DEFS)
    out.append('  </defs>\n\n')

    # pond
    out.append(f'  <rect width="{width}" height="{height}" rx="12" fill="#071525"/>\n')
    out.append(f'  <ellipse cx="250" cy="80" rx="270" ry="80" fill="url(#sheen)"/>\n')
    out.append(f'  <ellipse cx="650" cy="70" rx="230" ry="65" fill="url(#sheen2)"/>\n')
    out.append(f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" '
               'fill="none" stroke="#0f2d45"/>\n')

    mono = "font-family=\"'Fira Code','SFMono-Regular',Consolas,monospace\""

    # month labels
    out.append('\n  <!-- months -->\n')
    last_month = None
    for wi, week in enumerate(weeks):
        real = next((d for d in week if not d.get("outside")), None)
        if real is None:
            continue
        month = int(real["date"][5:7])
        if month != last_month:
            last_month = month
            x = grid_x + wi * pitch
            out.append(f'  <text x="{x}" y="20" {mono} font-size="9" fill="#5f7488">{MONTHS[month - 1]}</text>\n')

    # day labels
    out.append('\n  <!-- days -->\n')
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = grid_top + row * pitch + 9
        out.append(f'  <text x="{grid_x - 8}" y="{y}" {mono} font-size="9" fill="#5f7488" '
                   f'text-anchor="end">{label}</text>\n')

    # cells
    out.append('\n  <!-- contributions -->\n')
    for wi, week in enumerate(weeks):
        x = grid_x + wi * pitch
        for di, day in enumerate(week):
            if day.get("outside"):
                continue
            y = grid_top + di * pitch
            fill = LEVEL_COLORS.get(day["level"], LEVEL_COLORS[0])
            out.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}"/>\n')

    # koi swimming through the rows
    out.append('\n  <!-- koi -->\n  <g clip-path="url(#pondClip)">\n')
    for lane, (shape, scale, swims_left, dur, phase) in enumerate(LANE_FISH):
        lane_y = grid_top + lane * pitch - gap / 2
        out.append(fish_markup(shape, scale, swims_left, dur, phase, lane_y))
    for lane, shape, scale, swims_left, dur, phase in EXTRA_FISH:
        lane_y = grid_top + lane * pitch - gap / 2
        out.append(fish_markup(shape, scale, swims_left, dur, phase, lane_y))
    out.append('  </g>\n')

    # stats
    out.append('\n  <!-- stats -->\n')
    stats = (f'{total:,} contributions  ·  {streak}-day streak  ·  '
             f'peak {peak}  ·  {active} active days')
    out.append(f'  <text x="{grid_x}" y="142" {mono} font-size="9.5" fill="#6b8299" '
               f'letter-spacing="0.3">{stats}</text>\n')

    # legend
    out.append('\n  <!-- legend -->\n')
    legend_x = width - 18 - (28 + 5 * 13 + 4 + 26)
    out.append(f'  <text x="{legend_x}" y="142" {mono} font-size="9" fill="#5f7488">Less</text>\n')
    for i, level in enumerate(range(5)):
        x = legend_x + 28 + i * 13
        out.append(f'  <rect x="{x}" y="133" width="10" height="10" rx="2" '
                   f'fill="{LEVEL_COLORS[level]}"/>\n')
    out.append(f'  <text x="{legend_x + 28 + 5 * 13 + 4}" y="142" {mono} font-size="9" '
               f'fill="#5f7488">More</text>\n')

    out.append('</svg>\n')
    return "".join(out)


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a koi pond contribution heatmap SVG.")
    parser.add_argument("--user", default="astronishant", help="GitHub username")
    parser.add_argument("--out", default="assets/koi-heatmap.svg", help="output SVG path")
    args = parser.parse_args()

    try:
        html = fetch_html(args.user)
        days = parse_days(html)
    except Exception as exc:  # network / parse failure
        print(f"error: could not fetch contributions: {exc}", file=sys.stderr)
        return 1

    if len(days) < 100:
        print(
            f"error: only {len(days)} contribution days parsed — GitHub markup may have "
            "changed. Keeping the existing SVG.",
            file=sys.stderr,
        )
        return 1

    weeks = build_weeks(days)
    svg = render_svg(days, weeks, args.user)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(svg, encoding="utf-8")
    tmp_path.replace(out_path)

    total = sum(d["count"] for d in days)
    print(f"wrote {out_path} — {len(days)} days, {total:,} contributions, {len(weeks)} weeks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
