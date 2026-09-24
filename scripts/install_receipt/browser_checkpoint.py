"""Hold one original isolated helper for Ryan, then retain owned-stop evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from install_receipt.constants import CAPTURE_PROFILE_NAMES
from install_receipt.hashes import omit_raw_bytes
from install_receipt.launcher import InstalledHelperLauncher, read_token_with_note
from install_receipt.oracles import snapshot_with_measured_ids
from install_receipt.runner import OperatorRunner
from install_receipt.validation import C22ValidationError


def run_checkpoint(runner, *, profile_name="child-life", hold_seconds=None, observe=None, image_path=None):
    if profile_name not in CAPTURE_PROFILE_NAMES:
        raise C22ValidationError("unknown prepared browser profile")
    if hold_seconds is not None and not (0 <= hold_seconds <= 900):
        raise C22ValidationError("hold seconds must be 0..900")
    inputs = runner.load_inputs()
    profile = runner.receipt_root / "profiles" / profile_name
    port = inputs["isolated_port"]
    app = Path(inputs["installed_app"]["path"])
    if (app / "python" / "python.exe").is_file():
        from install_receipt.manifest import load_candidate_package_02
        from install_receipt.receipt_integrity import verify_installed_bindings
        integrity = verify_installed_bindings(app, load_candidate_package_02())
        if not integrity["ok"]:
            raise C22ValidationError("browser installed compiler inputs differ: " + repr(integrity["problems"]))
    image_path = Path(image_path or runner.receipt_root / "artifacts" / "browser-checkpoint.png").resolve()
    if not image_path.is_relative_to(runner.receipt_root.resolve()):
        raise C22ValidationError("browser image must be retained inside this receipt")
    evidence = runner.receipt_root / "evidence" / "browser-held-observation.json"
    if evidence.exists():
        raise C22ValidationError("browser observation already exists; preserve it and write a repair brief before rerunning")
    record = {"utc_start": datetime.now(timezone.utc).isoformat(), "profile": str(profile),
              "dashboard_url": f"http://127.0.0.1:{port}/dashboard", "status": "unobserved",
              "installed_credit": False, "screenshot": None,
              "required": ["UTC", "source and consent revision", "starts charged and allowance",
                           "visible in-flight/uncertain or terminal state"],
              "visual_review": "Ryan supplies an actual image; Astra compares it with these snapshots"}
    evidence.write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    launcher = InstalledHelperLauncher(runner)
    helper = None
    token = None
    error = None
    try:
        helper = launcher.start(profile_name="browser-held", isolated_profile=profile, isolated_port=port)
        record["helper_identity"] = helper["child"]
        token = read_token_with_note(app, profile).get("token")
        if not helper.get("health", {}).get("ok") or not token:
            raise C22ValidationError("browser helper health/token missing")
        record["before_observation"] = snapshot_with_measured_ids(profile, label="browser-held-before")
        evidence.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf8")
        print("Open " + record["dashboard_url"] + ". Capture the visible state and UTC; save the original image at " + str(image_path), flush=True)
        if observe is not None:
            observe(record)
        elif hold_seconds is None:
            input("Press Enter after saving the browser image to stop this owned helper: ")
        else:
            time.sleep(hold_seconds)
        record["after_observation"] = snapshot_with_measured_ids(profile, label="browser-held-after")
        record["helper_hold_completed"] = True
        if image_path.is_file():
            data = image_path.read_bytes()
            if data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"):
                record["screenshot"] = {"path": str(image_path), "bytes": len(data),
                                        "sha256": hashlib.sha256(data).hexdigest()}
                record["status"] = "pending_review"
            else:
                record["image_error"] = "retained bytes lack a PNG/JPEG signature; no visual credit"
    except BaseException as exc:
        error = exc
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if helper is not None:
            try:
                record["stop"] = launcher.stop_owned(port=port, identity=helper["child"], token=token, record=helper)
                stop = record["stop"]
                if not stop.get("stopped") or not stop.get("port_freed") or stop.get("guard_restore_deferred"):
                    raise C22ValidationError("browser helper cleanup is not affirmed")
                record["after_stop"] = snapshot_with_measured_ids(profile, label="browser-held-stopped")
            except BaseException as exc:
                error = error or exc
                record["status"] = "failed"
                record["cleanup_error"] = f"{type(exc).__name__}: {exc}"
        record["utc_end"] = datetime.now(timezone.utc).isoformat()
        evidence.write_text(json.dumps(omit_raw_bytes(record), indent=2, default=str) + "\n", encoding="utf8")
    if error is not None:
        raise error
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-root", required=True, type=Path)
    parser.add_argument("--profile-name", default="child-life", choices=CAPTURE_PROFILE_NAMES)
    parser.add_argument("--hold-seconds", type=float)
    parser.add_argument("--image-path", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args(argv)
    if not sys.flags.no_site or not sys.flags.isolated:
        raise C22ValidationError("start with system Python -I -S")
    stored = json.loads((args.receipt_root / "inputs.json").read_text(encoding="utf8"))
    runner = OperatorRunner.continue_existing(receipt_root=args.receipt_root, synthetic=args.synthetic,
        installed_app_path=stored["installed_app"]["path"], package_path=stored["package"]["path"],
        package_sha256=stored["package"]["sha256"], isolated_profile=stored["isolated_profile"],
        isolated_port=stored["isolated_port"],
        require_space=not args.synthetic, require_bundled_python=not args.synthetic)
    run_checkpoint(runner, profile_name=args.profile_name, hold_seconds=args.hold_seconds, image_path=args.image_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
