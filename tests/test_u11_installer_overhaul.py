"""U-11 installer first-run sequencing contract.

Run: python tests/test_u11_installer_overhaul.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ISS = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
VERIFY = (ROOT / "installer" / "verify_install.ps1").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
BITMAPS = (ROOT / "installer" / "generate_bitmaps.py").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_body() -> str:
    return ISS.split("procedure VerifyInstalledHelper();", 1)[1].split(
        "procedure CurStepChanged", 1
    )[0]


def run_section() -> str:
    return ISS.split("[Run]", 1)[1].split("[UninstallRun]", 1)[0]


def test_post_install_verification_does_not_spawn_ui() -> None:
    body = verify_body()
    require("pythonw.exe" not in body, "verification still launches pythonw.exe")
    require("server.py" not in body, "verification still launches the helper")
    require("RaiseException" not in body, "verification can still fail the install")
    require("mbInformation" in body, "verification warning is not downgraded")
    require("checking bundled files without starting helper" in body,
            "verification log does not state the files-only path")


def test_finish_launch_starts_helper_without_dashboard() -> None:
    section = run_section()
    require("--show-dashboard" not in section, "finish launch still forces the dashboard")
    require('Description: "Set up the browser button now";' in section,
            "finish checkbox does not match the first-run task")
    require("browser button" in ISS, "finish page copy does not point at the browser setup")


def test_welcome_page_is_dpi_safe() -> None:
    require("STEP 1 OF 4" not in ISS, "fake step tracker is still visible")
    require("WelcomePage.Surface.Color := C_CREAM;" in ISS, "welcome page does not use the cream surface")
    require("L.Top := ScaleY(Top);" in ISS, "welcome labels do not scale vertical position")
    require("L.Height := ScaleY(Height);" in ISS, "welcome labels do not scale height")
    require("SizeNextButtonToCaption('Let''s go ->')" in ISS,
            "welcome CTA is not sized from its caption (ASCII arrow)")
    require("Meas.AutoSize := True;" in ISS,
            "welcome CTA width is not measured at real DPI")


def test_verify_script_is_files_only_by_default() -> None:
    require("[switch]$ProbeHealth" in VERIFY, "verify script has no explicit health probe switch")
    require("if (-not $ProbeHealth)" in VERIFY, "verify script does not skip health by default")
    require("files-only install verification OK" in VERIFY, "verify script does not log files-only success")


def test_first_run_splash_suppresses_ready_toast() -> None:
    require("splash_spawned = True" in SERVER, "server does not track splash spawn")
    require("if splash_spawned:" in SERVER, "server does not branch on splash visibility")
    require("toast: skipped regular ready toast while first-run splash is visible" in SERVER,
            "ready toast is not suppressed while splash is visible")


def test_wizard_bitmaps_are_multi_scale() -> None:
    require('f"wizard-large-{pct}.bmp"' in BITMAPS, "large wizard filename template missing")
    require('f"wizard-small-{pct}.bmp"' in BITMAPS, "small wizard filename template missing")
    for pct in ("100", "125", "150", "200"):
        require(f"wizard-large-{pct}.bmp" in ISS, f"large wizard bitmap {pct}% not referenced")
        require(f"wizard-small-{pct}.bmp" in ISS, f"small wizard bitmap {pct}% not referenced")
        require(f"{pct}: " in BITMAPS, f"wizard bitmap scale {pct}% not generated")


def main() -> int:
    test_post_install_verification_does_not_spawn_ui()
    test_finish_launch_starts_helper_without_dashboard()
    test_welcome_page_is_dpi_safe()
    test_verify_script_is_files_only_by_default()
    test_first_run_splash_suppresses_ready_toast()
    test_wizard_bitmaps_are_multi_scale()
    print("ALL U-11 INSTALLER OVERHAUL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
