"""Exercise original source_subscriptions child-ownership methods.

Not a helper imitation and not a custom HTTP route. Writes under the declared
isolated profile's source_children directory using the product module from
the installed/source-runtime tree.

Injections:
  spawn_child            record intent, spawn sleeper, record_child_start
  launch_interrupt       record intent, do not spawn (unresolved stays)
  registration_failure   record intent, spawn sleeper, skip record_child_start
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--inject", required=True,
                        choices=("spawn_child", "launch_interrupt",
                                 "registration_failure"))
    parser.add_argument("--start-id", required=True)
    parser.add_argument("--instance", default="c22-instrument")
    parser.add_argument("--sleeper-seconds", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    profile = Path(args.profile)
    if not profile.is_absolute() or not profile.is_dir():
        raise SystemExit("child instrument: profile must be an existing absolute directory")
    if "5179" in str(args.start_id):
        raise SystemExit("child instrument: refusing 5179 in start id")

    # Product module must come from the installed/source-runtime tree on
    # sys.path[0] (the child's cwd / PYTHONPATH), not from a checkout overlay.
    import source_subscriptions as ss  # noqa: WPS433

    start_id = args.start_id
    instance = args.instance
    sleeper = None
    outcome = {
        "inject": args.inject,
        "start_id": start_id,
        "instance": instance,
        "profile": str(profile),
        "product_module": getattr(ss, "__file__", None),
        "methods": [
            "record_child_launch_intent",
            "record_child_start",
            "resolve_child_launch_intent",
        ],
    }
    ss.record_child_launch_intent(str(profile), start_id, instance)
    outcome["intent_recorded"] = True
    if args.inject == "launch_interrupt":
        outcome["unresolved_left"] = True
        outcome["spawned"] = False
    else:
        sleeper = subprocess.Popen(
            [sys.executable, "-B", "-c",
             f"import time; time.sleep({int(args.sleeper_seconds)})"]
        )
        outcome["spawned"] = True
        outcome["child_pid"] = sleeper.pid
        if args.inject == "registration_failure":
            outcome["record_child_start_skipped"] = True
            outcome["surviving_unregistered"] = True
        else:
            ss.record_child_start(str(profile), start_id, sleeper.pid, instance)
            outcome["record_child_start"] = True
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(outcome))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
