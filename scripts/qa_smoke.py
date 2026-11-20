"""One-command smoke test of the Uoink dashboard, extension, API, MCP and CLI.

    python scripts/qa_smoke.py                 # everything, fully hidden
    python scripts/qa_smoke.py --suites api    # just the API, MCP and CLI checks
    python scripts/qa_smoke.py --break search-500 --break search-hidden   # prove it goes red

What it does, for each library state it needs (seeded ~40 items, empty, 1,000 items):
seeds an isolated profile with made-up items (no network), starts the helper
hidden on a non-5179 port, runs the API/CLI checks and the Playwright suites
(Chromium, new headless mode), stops the helper, then prints a pass/fail
table and writes a contact sheet of every screenshot to <run>/index.html.

It never touches the normal Uoink library or port 5179. Dev only: nothing
here ships in the installer or the extension zip.

Setup once:  cd tests/e2e && npm ci && npx playwright install --no-shell chromium
(set PLAYWRIGHT_BROWSERS_PATH first to keep the browser out of your user profile).
"""
from __future__ import annotations

import argparse
import functools
import html
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
E2E = REPO / "tests" / "e2e"
sys.path.insert(0, str(E2E))

import qa_api_smoke  # noqa: E402  (stdlib only, no Uoink imports)

PRODUCTION_PORT = 5179
FIXTURE_HOST = "fixture.uoink.test"
SUITES = ("api", "dashboard", "extension")
FAULTS = ("search-500", "search-hidden")
VARIANTS = ("light-1280", "dark-1280", "light-390", "dark-390")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(msg: str) -> None:
    print(msg, flush=True)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(start: int = 18150, end: int = 18199) -> int:
    for port in range(start, end + 1):
        if port != PRODUCTION_PORT and not port_in_use(port):
            return port
    raise SystemExit("qa_smoke: no free port between 18150 and 18199")


def pick_port(asked: int | None) -> int:
    env_port = os.environ.get("UOINK_ISOLATED_PORT")
    port = asked or (int(env_port) if env_port and env_port.isdigit() else None) or free_port()
    if port == PRODUCTION_PORT:
        raise SystemExit("qa_smoke: refusing port 5179, which belongs to the normal Uoink helper")
    if port_in_use(port):
        raise SystemExit(f"qa_smoke: port {port} is already in use. Stop whatever runs there or pass --port.")
    return port


class FixtureServer:
    """Serves tests/e2e/fixtures on 127.0.0.1 for the extension's page save."""

    def __init__(self):
        handler = functools.partial(_QuietHandler, directory=str(E2E / "fixtures"))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def child_env(run_dir: Path, state: str, port: int) -> dict:
    """Environment for every Uoink child: isolated profile, port and app data."""
    profile = run_dir / "profiles" / state
    local = run_dir / "appdata" / state
    tmp = run_dir / "tmp"
    for d in (profile, local, tmp):
        d.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "UOINK_ISOLATED_PROFILE": str(profile),
        "UOINK_ISOLATED_PORT": str(port),
        "LOCALAPPDATA": str(local),
        "UOINK_DISABLE_AVAILABILITY_CHECK": "1",
        "UOINK_USAGE_SHARING": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "TMP": str(tmp),
        "TEMP": str(tmp),
    })
    return env


def seed(run_dir: Path, state: str, env: dict) -> dict:
    out = run_dir / "logs" / f"seed-{state}.log"
    proc = subprocess.run([sys.executable, str(E2E / "qa_seed.py"), "--state", state, "--fixture-host", FIXTURE_HOST],
                          cwd=str(REPO), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900, creationflags=NO_WINDOW)
    out.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), "")
    if proc.returncode != 0 or not line:
        raise SystemExit(f"qa_smoke: seeding '{state}' failed (exit {proc.returncode}). See {out}")
    result = json.loads(line)
    (run_dir / f"expect-{state}.json").write_text(json.dumps(result["expect"], indent=2), encoding="utf-8")
    return result


class Helper:
    """The isolated helper, started with no window and stopped at the end."""

    def __init__(self, run_dir: Path, state: str, env: dict, port: int, fixture_port: int, faults: list[str]):
        self.base = f"http://127.0.0.1:{port}"
        self.env = env
        self.profile = Path(env["UOINK_ISOLATED_PROFILE"])
        self.log_path = run_dir / "logs" / f"helper-{state}.log"
        cmd = [sys.executable, str(E2E / "qa_helper.py"), "--fixture", f"{FIXTURE_HOST}={fixture_port}"]
        for fault in faults:
            cmd += ["--break", fault]
        self.cmd = cmd
        self.proc = None

    def start(self, timeout: float = 90.0):
        self._log = self.log_path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(self.cmd, cwd=str(REPO), env=self.env, stdout=self._log,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit(f"qa_smoke: the helper exited early (code {self.proc.returncode}). See {self.log_path}")
            try:
                with _OPENER.open(self.base + "/health", timeout=2) as resp:
                    data = json.loads(resp.read())
                if data.get("ok") and data.get("pid") == self.proc.pid and (self.profile / "token.txt").exists():
                    return data
            except (OSError, ValueError):
                pass
            time.sleep(0.4)
        self.stop()
        raise SystemExit(f"qa_smoke: the helper did not answer /health in {timeout:.0f}s. See {self.log_path}")

    def stop(self):
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            req = urllib.request.Request(self.base + "/helper/quit", data=b"{}", method="POST", headers={
                "X-Uoink-Token": (self.profile / "token.txt").read_text(encoding="utf-8").strip(),
                "Content-Type": "application/json"})
            _OPENER.open(req, timeout=5).close()
        except (OSError, urllib.error.URLError):
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._log.close()


def node_command() -> list[str] | None:
    node = shutil.which("node")
    cli = E2E / "node_modules" / "@playwright" / "test" / "cli.js"
    if not node or not cli.exists():
        return None
    return [node, str(cli)]


def run_playwright(run_dir: Path, label: str, state: str, base: str, profile: Path, fixture_port: int,
                   projects: list[str], grep: str, headed: bool) -> Path:
    cmd = node_command()
    report = run_dir / "reports" / f"{label}.json"
    env = dict(os.environ)
    env.update({
        "UOINK_QA_RUN_DIR": str(run_dir), "UOINK_QA_BASE_URL": base, "UOINK_QA_PROFILE": str(profile),
        "UOINK_QA_STATE": state, "UOINK_QA_REPORT_LABEL": label, "UOINK_QA_FIXTURE_PORT": str(fixture_port),
        "UOINK_QA_FIXTURE_HOST": FIXTURE_HOST, "UOINK_E2E_EXTENSION": "headless",
        "FORCE_COLOR": "0", "NO_COLOR": "1",
    })
    env.pop("UOINK_E2E_HEADED", None)
    if headed:
        env["UOINK_E2E_HEADED"] = "1"
    args = [*cmd, "test", "--config", str(E2E / "playwright.config.mjs"), "--grep", grep]
    for p in projects:
        args += ["--project", p]
    out = run_dir / "logs" / f"playwright-{label}.log"
    with out.open("w", encoding="utf-8") as fh:
        subprocess.run(args, cwd=str(E2E), env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=3600,
                       creationflags=NO_WINDOW)
    return report


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def error_summary(message: str) -> str:
    """First line of a Playwright error plus any received list items, without colour codes."""
    lines = [ln.rstrip() for ln in _ANSI.sub("", message).splitlines() if ln.strip()]
    if not lines:
        return ""
    added = [ln.strip()[1:].strip().rstrip(",") for ln in lines if ln.startswith("+  ")]
    text = lines[0] + (" -> " + "; ".join(added) if added else "")
    return text[:600]


def read_report(report: Path, suite_for) -> list[dict]:
    """Flatten a Playwright JSON report into result rows."""
    if not report.exists():
        return [{"suite": "playwright", "name": f"report {report.name} missing (see logs)", "ok": False,
                 "status": "failed", "detail": "", "known": [], "seconds": 0, "project": ""}]
    data = json.loads(report.read_text(encoding="utf-8"))
    rows = []

    def walk(suite, file):
        for spec in suite.get("specs", []):
            for t in spec.get("tests", []):
                results = t.get("results") or [{}]
                last = results[-1]
                status = last.get("status") or ("skipped" if t.get("status") == "skipped" else "failed")
                notes = [a for a in t.get("annotations", []) + last.get("annotations", [])]
                known = [a.get("description", "") for a in notes if a.get("type") == "known-issue"]
                skip_reason = next((a.get("description", "") for a in notes if a.get("type") == "skip"), "")
                err = error_summary((last.get("error") or {}).get("message", "") or "")
                rows.append({
                    "suite": suite_for(file), "name": spec.get("title", ""), "project": t.get("projectName", ""),
                    "status": status, "ok": status in ("passed", "skipped"),
                    "detail": skip_reason if status == "skipped" else err,
                    "known": sorted(set(known)), "seconds": round((last.get("duration") or 0) / 1000, 1),
                    "timing": [a.get("description", "") for a in notes if a.get("type") == "timing"],
                })
        for child in suite.get("suites", []):
            walk(child, file)

    for top in data.get("suites", []):
        walk(top, top.get("file", ""))
    for err in data.get("errors", []):
        rows.append({"suite": "playwright", "name": "run error", "project": "", "status": "failed", "ok": False,
                     "detail": (err.get("message") or "")[:300], "known": [], "seconds": 0})
    return rows


def suite_of(file: str) -> str:
    return "a11y" if "a11y" in file else "extension" if "extension" in file else "dashboard"


def write_contact_sheet(run_dir: Path, results: list[dict], verdict: str) -> Path:
    manifest = run_dir / "shots" / "manifest.jsonl"
    shots = [json.loads(ln) for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if manifest.exists() else []
    order = [*VARIANTS, "extension"]
    groups: dict[tuple, dict] = {}
    for s in shots:
        groups.setdefault((s["state"], s["flow"]), {})[s["project"]] = s["file"]
    failed = [r for r in results if not r["ok"]]
    known = sorted({k for r in results for k in r.get("known", [])})
    esc = html.escape
    rows_html = "".join(
        f"<tr class='{ 'bad' if not r['ok'] else ''}'><td>{esc(r['suite'])}</td><td>{esc(r.get('state', ''))}</td>"
        f"<td>{esc(r.get('project', ''))}</td><td>{esc(r['name'])}</td><td>{esc(r.get('status', 'passed' if r['ok'] else 'failed'))}</td>"
        f"<td>{esc(r.get('detail', ''))}</td></tr>" for r in results)
    sections = []
    for (state, flow), files in sorted(groups.items()):
        cells = "".join(
            f"<figure><a href='{esc(files[p])}'><img loading='lazy' src='{esc(files[p])}' alt='{esc(flow)} at {esc(p)}'></a>"
            f"<figcaption>{esc(p)}</figcaption></figure>" for p in order if p in files)
        sections.append(f"<section><h2>{esc(state)} / {esc(flow)}</h2><div class='row'>{cells}</div></section>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Uoink QA smoke</title>
<style>
:root {{ color-scheme: light dark; --bg:#fff; --fg:#1d1d1f; --line:#ddd; --bad:#fde8e8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#18181a; --fg:#eee; --line:#333; --bad:#4a1f1f; }} }}
body {{ font: 14px/1.4 system-ui, sans-serif; margin: 16px; background: var(--bg); color: var(--fg); }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
td, th {{ border-bottom: 1px solid var(--line); padding: 4px 6px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
tr.bad td {{ background: var(--bad); }}
.row {{ display: flex; gap: 12px; overflow-x: auto; align-items: flex-start; }}
figure {{ margin: 0; min-width: 0; flex: 0 0 auto; }}
figure img {{ display: block; max-height: 420px; max-width: 360px; border: 1px solid var(--line); }}
figcaption {{ font-size: 12px; opacity: .8; }}
h2 {{ font-size: 15px; margin: 24px 0 8px; }}
</style></head><body>
<h1>Uoink QA smoke: {esc(verdict)}</h1>
<p>{len(results)} checks, {len(failed)} failed, {len(known)} known issues. Run folder: {esc(str(run_dir))}</p>
{"<h2>Known issues (reported, not failing)</h2><ul>" + "".join(f"<li>{esc(k)}</li>" for k in known) + "</ul>" if known else ""}
<details {"open" if failed else ""}><summary>All results</summary><table><tr><th>Suite</th><th>State</th><th>Variant</th><th>Check</th><th>Result</th><th>Detail</th></tr>{rows_html}</table></details>
{"".join(sections)}
</body></html>"""
    out = run_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


def print_table(results: list[dict], elapsed: dict) -> None:
    keys = []
    for r in results:
        k = (r["suite"], r.get("state", ""))
        if k not in keys:
            keys.append(k)
    log("")
    log(f"{'suite':<11}{'state':<9}{'pass':>6}{'fail':>6}{'skip':>6}{'known':>7}{'time':>9}")
    for suite, state in keys:
        rows = [r for r in results if r["suite"] == suite and r.get("state", "") == state]
        passed = sum(1 for r in rows if r.get("status", "passed" if r["ok"] else "failed") == "passed")
        failed = sum(1 for r in rows if not r["ok"])
        skipped = sum(1 for r in rows if r.get("status") == "skipped")
        known = len({k for r in rows for k in r.get("known", [])})
        secs = elapsed.get((suite, state), sum(r.get("seconds", 0) for r in rows))
        log(f"{suite:<11}{state:<9}{passed:>6}{failed:>6}{skipped:>6}{known:>7}{secs:>8.0f}s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="One-command Uoink smoke test (isolated, hidden).")
    ap.add_argument("--suites", default=",".join(SUITES), help="comma list of api,dashboard,extension")
    ap.add_argument("--run-dir", type=Path, help="where logs, screenshots and the contact sheet go")
    ap.add_argument("--port", type=int, help="isolated helper port (never 5179)")
    ap.add_argument("--break", dest="faults", action="append", default=[], choices=FAULTS,
                    help="break one thing on purpose to prove the suite goes red")
    ap.add_argument("--headed", action="store_true",
                    help="run the extension tests in a visible window (UOINK_E2E_HEADED=1)")
    ap.add_argument("--variants", default=",".join(VARIANTS), help="dashboard variants to run")
    args = ap.parse_args(argv)
    suites = [s for s in args.suites.split(",") if s]
    bad = [s for s in suites if s not in SUITES]
    if bad:
        ap.error(f"unknown suite(s): {', '.join(bad)}")
    variants = [v for v in args.variants.split(",") if v in VARIANTS]
    run_dir = (args.run_dir or REPO / "_scratch" / "qa-smoke" / datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
    for sub in ("logs", "reports", "shots"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    port = pick_port(args.port)
    browser_suites = [s for s in suites if s in ("dashboard", "extension")]
    if browser_suites and not node_command():
        raise SystemExit("qa_smoke: Playwright is not installed. Run: cd tests/e2e && npm ci && "
                         "npx playwright install --no-shell chromium")
    log(f"Uoink QA smoke: port {port}, run folder {run_dir}")
    if args.faults:
        log(f"Breaking on purpose: {', '.join(args.faults)} (this run should FAIL)")

    states = ["seeded"]
    if "dashboard" in suites:
        states += ["empty", "big"]
    elif "api" in suites:
        states += ["empty"]
    results: list[dict] = []
    elapsed: dict = {}
    started_all = time.monotonic()
    with FixtureServer() as fixture:
        for state in states:
            env = child_env(run_dir, state, port)
            t0 = time.monotonic()
            seeded = seed(run_dir, state, env)
            log(f"[{state}] seeded {seeded['items']} items in {time.monotonic() - t0:.0f}s")
            helper = Helper(run_dir, state, env, port, fixture.port, args.faults)
            health = helper.start()
            log(f"[{state}] helper {health.get('version')} up, pid {health.get('pid')}")
            try:
                if "api" in suites:
                    t0 = time.monotonic()
                    client = qa_api_smoke.Client(helper.base, helper.profile)
                    rows = qa_api_smoke.api_checks(client, seeded["expect"], state)
                    for r in rows:
                        r["state"] = state
                    results += rows
                    elapsed[("api", state)] = time.monotonic() - t0
                    if state == "seeded":
                        t0 = time.monotonic()
                        rows = qa_api_smoke.cli_checks(REPO, env, seeded["expect"], state)
                        for r in rows:
                            r["state"] = state
                        results += rows
                        elapsed[("cli", state)] = time.monotonic() - t0
                    log(f"[{state}] api/cli checks done")
                if "dashboard" in suites and variants:
                    t0 = time.monotonic()
                    report = run_playwright(run_dir, f"dashboard-{state}", state, helper.base, helper.profile,
                                            fixture.port, variants, f"@{state}", False)
                    rows = read_report(report, suite_of)
                    for r in rows:
                        r["state"] = state
                    results += rows
                    took = time.monotonic() - t0
                    for suite in {r["suite"] for r in rows}:
                        elapsed[(suite, state)] = took if suite == "dashboard" else 0
                    log(f"[{state}] browser suites done in {took:.0f}s")
                if "extension" in suites and state == "seeded":
                    t0 = time.monotonic()
                    report = run_playwright(run_dir, "extension", state, helper.base, helper.profile,
                                            fixture.port, ["extension"], "@extension", args.headed)
                    rows = read_report(report, suite_of)
                    for r in rows:
                        r["state"] = state
                    results += rows
                    elapsed[("extension", state)] = time.monotonic() - t0
                    log(f"[{state}] extension suite done")
            finally:
                helper.stop()
    if port_in_use(port):
        log(f"warning: something still answers on port {port} after the run")

    failed = [r for r in results if not r["ok"]]
    verdict = "FAIL" if failed or not results else "PASS"
    sheet = write_contact_sheet(run_dir, results, verdict)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print_table(results, elapsed)
    if failed:
        log("\nFailures:")
        for r in failed:
            where = " / ".join(x for x in (r["suite"], r.get("state", ""), r.get("project", "")) if x)
            log(f"  - {where} / {r['name']}: {r.get('detail', '')[:200]}")
    known = sorted({k for r in results for k in r.get("known", [])})
    if known:
        log(f"\nKnown issues reported (not failing): {len(known)}")
        for k in known:
            log(f"  - {k[:200]}")
    skipped = [r for r in results if r.get("status") == "skipped"]
    if skipped:
        log(f"\nSkipped: {len(skipped)}")
        for r in {(r['name'], r.get('detail', '')) for r in skipped}:
            log(f"  - {r[0]}: {r[1][:160]}")
    log(f"\nRESULT: {verdict} in {time.monotonic() - started_all:.0f}s")
    log(f"Contact sheet: {sheet}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
