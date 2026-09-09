"""Operator CLI for the C22 receipt kit.

Required explicit inputs: installed app path, package path, package hash,
isolated profile, isolated port, receipt root.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = KIT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from install_receipt.evidence import build_verdict  # noqa: E402
from install_receipt.launcher import launch_argv  # noqa: E402
from install_receipt.manifest import load_manifest, write_example  # noqa: E402
from install_receipt.runner import OperatorRunner  # noqa: E402
from install_receipt.scenarios import ScenarioRunner, scenario_table  # noqa: E402
from install_receipt.validation import C22ValidationError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_required(p):
        p.add_argument("--installed-app", required=True)
        p.add_argument("--package", required=True)
        p.add_argument("--package-sha256", required=True)
        p.add_argument("--isolated-profile", required=True)
        p.add_argument("--isolated-port", required=True, type=int)
        p.add_argument("--receipt-root", required=True)
        p.add_argument("--manifest")
        p.add_argument("--synthetic", action="store_true",
                       help="labeled non-installed instrument check")
        p.add_argument("--allow-ordinary-user", action="store_true",
                       help="only for synthetic instrument checks")
        p.add_argument("--fixture-port", type=int, default=18080)

    prep = sub.add_parser("prepare", help="create a fresh receipt root")
    add_required(prep)

    sub.add_parser("write-example-manifest",
                   help="write the unsealed manifest template")
    ex = sub.choices["write-example-manifest"]
    ex.add_argument("--out", required=True)

    lst = sub.add_parser("list-scenarios")
    lst.add_argument("--json", action="store_true")

    run = sub.add_parser("run", help="run one scenario or all")
    add_required(run)
    run.add_argument("--scenario", default="all")
    run.add_argument("--continue-existing-receipt", action="store_true",
                     help="reuse a prepared receipt; do not overwrite completed scenarios")

    collect = sub.add_parser("collect", help="write verdict input from a receipt")
    collect.add_argument("--receipt-root", required=True)

    plan = sub.add_parser("plan-install", help="print the isolated Inno argv")
    add_required(plan)
    plan.add_argument("--continue-existing-receipt", action="store_true")

    before = sub.add_parser(
        "prepare-before-install",
        help="create a receipt before the app exists; later run continues it")
    before.add_argument("--intended-app", required=True)
    before.add_argument("--package", required=True)
    before.add_argument("--package-sha256", required=True)
    before.add_argument("--isolated-profile", required=True)
    before.add_argument("--isolated-port", required=True, type=int)
    before.add_argument("--receipt-root", required=True)
    before.add_argument("--manifest")
    before.add_argument("--synthetic", action="store_true")
    before.add_argument("--allow-ordinary-user", action="store_true")
    before.add_argument("--fixture-port", type=int, default=18080)
    before.add_argument("--kit-root", help="explicit kit import root for later bundled run")

    argv = sub.add_parser("print-launch-argv")
    add_required(argv)
    return parser


def _runner(args) -> OperatorRunner:
    synthetic = bool(getattr(args, "synthetic", False))
    continue_existing = bool(getattr(args, "continue_existing_receipt", False))
    if continue_existing:
        return OperatorRunner.continue_existing(
            receipt_root=args.receipt_root,
            installed_app_path=getattr(args, "installed_app", None),
            package_path=getattr(args, "package", None),
            package_sha256=getattr(args, "package_sha256", None),
            isolated_profile=getattr(args, "isolated_profile", None),
            isolated_port=getattr(args, "isolated_port", None),
            synthetic=synthetic,
            require_space=not synthetic,
            require_bundled_python=not synthetic,
        )
    return OperatorRunner.create(
        receipt_root=args.receipt_root,
        installed_app_path=args.installed_app,
        package_path=args.package,
        package_sha256=args.package_sha256,
        isolated_profile=args.isolated_profile,
        isolated_port=args.isolated_port,
        manifest_path=getattr(args, "manifest", None),
        synthetic=synthetic,
        require_space=not synthetic,
        require_bundled_python=not synthetic,
        skip_ordinary_user_check=synthetic or bool(
            getattr(args, "allow_ordinary_user", False)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "write-example-manifest":
            path = write_example(Path(args.out))
            print(path)
            return 0
        if args.cmd == "list-scenarios":
            rows = scenario_table()
            print(json.dumps(rows, indent=2) if args.json else
                  "\n".join(r["id"] + " — " + r["as7"] for r in rows))
            return 0
        if args.cmd == "collect":
            root = Path(args.receipt_root)
            outcomes = {}
            evidence = root / "evidence"
            if evidence.is_dir():
                for path in evidence.glob("*.json"):
                    if path.name == "verdict.json":
                        continue
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict) and data.get("id"):
                        outcomes[data["id"]] = data
            inputs = {}
            if (root / "inputs.json").is_file():
                inputs = json.loads((root / "inputs.json").read_text(
                    encoding="utf-8"))
            verdict = build_verdict(
                root, outcomes, synthetic=bool(inputs.get("synthetic")))
            print(json.dumps(verdict, indent=2))
            return 0
        if args.cmd == "prepare-before-install":
            runner = OperatorRunner.prepare_before_install(
                receipt_root=args.receipt_root,
                intended_app_path=args.intended_app,
                package_path=args.package,
                package_sha256=args.package_sha256,
                isolated_profile=args.isolated_profile,
                isolated_port=args.isolated_port,
                manifest_path=getattr(args, "manifest", None),
                synthetic=bool(args.synthetic),
                require_space=not bool(args.synthetic),
                skip_ordinary_user_check=bool(args.synthetic) or bool(
                    args.allow_ordinary_user),
            )
            scenarios = ScenarioRunner(
                runner, fixture_port=int(getattr(args, "fixture_port", 18080)))
            try:
                prepared = scenarios.prepare_profiles()
            finally:
                scenarios.close()
            commands = operator_commands(
                receipt_root=runner.receipt_root,
                intended_app=args.intended_app,
                package=args.package,
                package_sha256=args.package_sha256,
                isolated_profile=args.isolated_profile,
                isolated_port=args.isolated_port,
                manifest=getattr(args, "manifest", None),
                kit_root=getattr(args, "kit_root", None),
                synthetic=bool(args.synthetic),
            )
            (runner.receipt_root / "operator_commands.json").write_text(
                json.dumps(commands, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({
                "receipt_root": str(runner.receipt_root),
                "prepare_before_install": True,
                "intended_app": runner.load_inputs()["installed_app"],
                "prepared": prepared,
                "operator_commands": commands,
            }, indent=2, default=str))
            return 0
        runner = _runner(args)
        if args.cmd == "prepare":
            scenarios = ScenarioRunner(runner, fixture_port=args.fixture_port)
            try:
                prepared = scenarios.prepare_profiles()
            finally:
                scenarios.close()
            print(json.dumps({
                "receipt_root": str(runner.receipt_root),
                "prepared": prepared,
            }, indent=2))
            return 0
        if args.cmd == "plan-install":
            manifest = load_manifest(args.manifest)
            print(json.dumps(runner.plan_inno(manifest), indent=2))
            return 0
        if args.cmd == "print-launch-argv":
            inputs = runner.load_inputs()
            argv_list = launch_argv(
                Path(inputs["installed_app"]["path"]),
                isolated_profile=Path(inputs["isolated_profile"]),
                isolated_port=inputs["isolated_port"],
                synthetic=runner.synthetic,
            )
            print(json.dumps(argv_list, indent=2))
            return 0
        if args.cmd == "run":
            scenarios = ScenarioRunner(runner, fixture_port=args.fixture_port)
            try:
                completed = set(runner.completed_scenario_ids())
                scenarios.prepare_profiles()  # resumes without overwrite when locked
                if args.scenario == "all":
                    outcomes = scenarios.run_all(skip_ids=completed)
                else:
                    if args.scenario in completed:
                        raise C22ValidationError(
                            f"refusing to overwrite completed scenario {args.scenario}")
                    outcomes = {args.scenario: scenarios.run_one(args.scenario)}
            finally:
                scenarios.close()
            verdict = build_verdict(
                runner.receipt_root, outcomes, synthetic=runner.synthetic)
            print(json.dumps({
                "receipt_root": str(runner.receipt_root),
                "verdict": verdict,
            }, indent=2, default=str))
            claimed = verdict["installed_pass_claimed"]
            return 1 if claimed or verdict["counts"]["fail"] else 0
    except C22ValidationError as exc:
        print("C22 refuse:", exc, file=sys.stderr)
        return 2
    return 0


def operator_commands(*, receipt_root, intended_app, package, package_sha256,
                      isolated_profile, isolated_port, manifest=None,
                      kit_root=None, synthetic: bool = False) -> dict:
    """Exact stdlib-only preinstall and bundled postinstall commands.

    Preinstall may use system Python -I -S. Postinstall uses the bundled
    interpreter with an explicit kit import root and original product routes.
    """
    kit_dir = Path(__file__).resolve().parent
    scripts_dir = kit_dir.parent
    kit_import_root = str(Path(kit_root).resolve() if kit_root else scripts_dir)
    cli_path = str(Path(__file__).resolve())
    preinstall = [
        sys.executable, "-I", "-S", cli_path,
        "prepare-before-install",
        "--intended-app", str(intended_app),
        "--package", str(package),
        "--package-sha256", str(package_sha256),
        "--isolated-profile", str(isolated_profile),
        "--isolated-port", str(isolated_port),
        "--receipt-root", str(receipt_root),
    ]
    if manifest:
        preinstall.extend(["--manifest", str(manifest)])
    if synthetic:
        preinstall.append("--synthetic")
    bundled = Path(intended_app) / "python" / "python.exe"
    postinstall = [
        str(bundled), "-B", "-s", "-c",
        (
            "import sys; sys.path.insert(0, %r); "
            "from install_receipt.cli import main; "
            "raise SystemExit(main(sys.argv[1:]))"
            % kit_import_root
        ),
        "run",
        "--installed-app", str(intended_app),
        "--package", str(package),
        "--package-sha256", str(package_sha256),
        "--isolated-profile", str(isolated_profile),
        "--isolated-port", str(isolated_port),
        "--receipt-root", str(receipt_root),
        "--continue-existing-receipt",
        "--scenario", "all",
    ]
    if manifest:
        postinstall.extend(["--manifest", str(manifest)])
    return {
        "preinstall_stdlib": preinstall,
        "postinstall_bundled": postinstall,
        "kit_import_root": kit_import_root,
        "bundled_python": str(bundled),
        "install_unexecuted_until_ryan": True,
        "browser_unexecuted_until_ryan": True,
        "upgrade_unexecuted_until_ryan": True,
        "same_version_reinstall_is_not_upgrade": True,
        "marker_installer_owned": True,
        "profile_switch_is_cli_binding": True,
        "installed_credit": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
