"""Generate the city picture.

    GH_TOKEN=... python3 city/generate.py --out dist/city.svg

Environment:
    GH_TOKEN            token with `repo` and `read:user` scopes (private repositories included)
    CITY_LAT, CITY_LON  where the weather comes from (default: central Tokyo)
    CITY_TZ             time zone for hours and dates (default: Asia/Tokyo)
    CITY_IGNORE_LANGS   comma-separated languages to leave out, e.g. "HTML,CSS"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fetch   # noqa: E402
import render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="dist/city.svg", help="where to write the SVG")
    parser.add_argument("--data", help="render from a previously dumped JSON file instead of fetching")
    parser.add_argument("--dump", help="also write the collected data to this JSON file (keep it out of the repository)")
    args = parser.parse_args()

    if args.data:
        data = json.loads(Path(args.data).read_text())
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("GH_TOKEN is not set", file=sys.stderr)
            return 1
        data = fetch.collect(
            token,
            lat=float(os.environ.get("CITY_LAT") or 35.68),
            lon=float(os.environ.get("CITY_LON") or 139.77),
            tzname=os.environ.get("CITY_TZ") or "Asia/Tokyo",
            ignore={name.strip() for name in (os.environ.get("CITY_IGNORE_LANGS") or "").split(",") if name.strip()},
        )
    if args.dump:
        Path(args.dump).write_text(json.dumps(data, ensure_ascii=False, indent=1))

    svg = render.render(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg)
    print(f"wrote {out} ({len(svg) // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
