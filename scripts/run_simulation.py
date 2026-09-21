#!/usr/bin/env python
"""CLI: run the council simulation for one or more meeting dates.

Usage:
    uv run python scripts/run_simulation.py 2022-07-21 [--rounds 2]
        [--generator gateway|openai_compat] [--generator-model openai/gpt-4o-mini]
        [--out data/processed/simulations]

Requires AI_GATEWAY_API_KEY in .env.local (extractor, always Jev via the
Vercel AI Gateway). For --generator openai_compat also set
OPENAI_COMPAT_BASE_URL, OPENAI_COMPAT_API_KEY (optional) and
OPENAI_COMPAT_MODEL.

Note: memos are not committed to the repository (data/ stays untracked);
build them first with `uv run python -m synthetic_council.memo` (needs the
collected datasets) or point --memos-dir at an existing memos/ directory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from synthetic_council.simulation.config import SimulationConfig
from synthetic_council.simulation.runner import run_simulation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dates", nargs="+", help="meeting dates, YYYY-MM-DD")
    p.add_argument("--memos-dir", type=Path, default=None)
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument(
        "--generator",
        choices=["gateway", "openai_compat"],
        default="gateway",
    )
    p.add_argument("--generator-model", default="openai/gpt-4o-mini")
    p.add_argument("--extractor-model", default="typesafe-ai/jev")
    p.add_argument("--out", type=Path, default=Path("data/processed/simulations"))
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="validate config + memos, then exit without any API calls",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not os.environ.get("AI_GATEWAY_API_KEY"):
        # local .env.local convenience load (never committed)
        env_local = Path(".env.local")
        if env_local.exists():
            for line in env_local.read_text().splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    if not os.environ.get("AI_GATEWAY_API_KEY"):
        print("AI_GATEWAY_API_KEY is not set (put it in .env.local)", file=sys.stderr)
        return 2

    cfg = SimulationConfig(
        memos_dir=args.memos_dir
        if args.memos_dir
        else Path("data/processed/memos"),
        generator_backend=args.generator,
        generator_model=args.generator_model,
        extractor_model=args.extractor_model,
        n_rounds=args.rounds,
    )

    from synthetic_council.simulation.runner import meeting_memos

    for d in args.dates:
        n = len(meeting_memos(cfg.memos_dir, d))
        print(f"{d}: {n} member memos found")

    if args.dry_run:
        print("dry-run OK: config valid, memos found; no API calls made")
        return 0

    written = asyncio.run(run_simulation(args.dates, cfg, args.out))
    for path in written:
        payload = json.loads(path.read_text())
        cons = payload["consensus"]
        changed = [a["person"] for a in payload["agents"] if a["deltas"]["position_changed"]]
        print(
            f"{payload['meeting_date']}: {payload['n_agents']} agents, "
            f"{payload['n_rounds']} rounds; balance {cons['before']} -> {cons['after']}; "
            f"position changes: {changed or 'none'}"
        )
        print(f"  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
