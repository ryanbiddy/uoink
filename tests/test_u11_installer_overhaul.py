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
ICON = (ROOT / "installer" / "generate_icon.py").read_text(encoding="utf-8")


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
    require('Description: "Open Uoink and add the Chrome button";' in section,
            "finish checkbox does not match the first-run task")
    require("browser button" in ISS, "finish page copy does not point at the browser setup")


def pascal_routine(header: str) -> str:
    """Body of one top-level routine in the [Code] section: from its header up
    to the first line that is exactly `end;`."""
    start = ISS.index(header)
    end = ISS.index("\nend;", start)
    return ISS[start:end]


def test_welcome_page_is_dpi_safe() -> None:
    require("STEP 1 OF 4" not in ISS, "fake step tracker is still visible")
    require("WizardBackColor=#FFF4EC" in ISS, "wizard canvas is not the cream of the download page")
    require("WizardBackColorDynamicDark=#15110D" in ISS, "dark mode canvas is not the app icon ink")
    require("WizardStyle=modern dynamic windows11 hidebevels" in ISS,
            "wizard does not follow the system light/dark setting without bevels")
    build = pascal_routine("procedure BuildWelcomePage();")
    require("ScaleX(48)" in build and "ScaleY(140)" in build,
            "welcome labels are not positioned with ScaleX/ScaleY")
    require("SetBounds(Left, ScaleY(" in build, "welcome labels do not scale vertical position and height")
    require("ScaleX(80)" in build and "ScaleY(80)" in build, "welcome icon is not sized with ScaleX/ScaleY")
    require("IsDarkInstallMode()" in ISS, "custom label colors do not follow dark mode")
    require("SizeNextButtonToCaption(ActionCaption())" in ISS,
            "welcome CTA is not sized from its caption (ASCII caption)")
    require("Let''s go" not in ISS and "Build from receipts" not in ISS,
            "old welcome copy is still in the installer")
    require("Meas.AutoSize := True;" in ISS,
            "welcome CTA width is not measured at real DPI")


def test_next_button_caption_is_never_restored_from_initialize_wizard() -> None:
    """Shipped bug: InitializeWizard saved NextButton.Caption (still "*" at that
    point) and CurPageChanged wrote it back on every other page, so Next,
    Install and Finish all read "*". Inno sets its own captions per page."""
    init = pascal_routine("procedure InitializeWizard();")
    require("NextButton.Caption" not in init, "InitializeWizard reads the Next button caption")
    require("DefaultNextCaption" not in ISS, "a captured Next caption variable is back")
    page = pascal_routine("procedure CurPageChanged(CurPageID: Integer);")
    require("NextButton.Caption" not in page, "CurPageChanged assigns the Next button caption directly")
    for line in page.splitlines():
        if "NextButton.Caption" in line:
            require(False, "CurPageChanged touches NextButton.Caption: " + line.strip())
    # Only the measured helper may set a caption, and only from a literal or a
    # message, never from state saved before the wizard exists.
    helper = pascal_routine("procedure SizeNextButtonToCaption(const Cap: String);\nvar")
    require("NextButton.Caption := Cap;" in helper, "the sizing helper no longer sets the caption")


def test_one_click_install_skips_pages_unless_customize_is_ticked() -> None:
    skip = pascal_routine("function ShouldSkipPage(PageID: Integer): Boolean;")
    require("not CustomizeChosen" in skip, "skipped pages do not depend on the customize box")
    for page in ("wpSelectDir", "wpSelectTasks", "wpReady"):
        require(page in skip, page + " is not skipped in the one-click flow")
    require("not IsolatedInstall()" in skip, "isolated mode would lose its pages")
    require("CustomizeBox.Checked := False;" in ISS, "the customize box is not unchecked by default")
    require("'Choose the install folder and shortcuts'" in ISS, "customize box copy changed")
    require("'Update Uoink'" in ISS and "WizardForm.PrevAppDir" in ISS, "update title is not wired")
    require("SetupWindowTitle={#AppName} Setup" in ISS, "window title is not 'Uoink Setup'")


def test_isolated_welcome_button_says_next() -> None:
    """Isolated installs keep every page, so the Welcome button must not say
    Install there (it leads to the folder page), and the customize box is hidden."""
    caption = pascal_routine("function ActionCaption(): String;")
    require("if CustomizeChosen or IsolatedInstall() then" in caption,
            "isolated Welcome button would read Install but lead to the folder page")
    require("CustomizeBox.Visible := not IsolatedInstall();" in pascal_routine("procedure BuildWelcomePage();"),
            "the customize box shows in isolated mode, where it does nothing")


def test_installer_copy_avoids_old_and_banned_words() -> None:
    messages = ISS.split("[Messages]", 1)[1].split("[Languages]", 1)[0]
    for word in ("corpus", "receipts", "seamless", "robust", "leverage", "delve", "straightforward"):
        require(word not in messages.lower(), "banned word in installer messages: " + word)
    require("--" not in messages.replace("; ", ""), "double hyphen (em dash stand-in) in installer messages")


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
    require('f"wizard-large-{pct}.png"' in BITMAPS, "large wizard filename template missing")
    require('f"wizard-small-{pct}.png"' in BITMAPS, "small wizard filename template missing")
    require('f"wizard-large-dark-{pct}.png"' in BITMAPS, "dark large wizard filename template missing")
    require('f"wizard-small-dark-{pct}.png"' in BITMAPS, "dark small wizard filename template missing")
    for pct in ("100", "125", "150", "200"):
        require(f"wizard-large-{pct}.png" in ISS, f"large wizard image {pct}% not referenced")
        require(f"wizard-small-{pct}.png" in ISS, f"small wizard image {pct}% not referenced")
        require(f"wizard-large-dark-{pct}.png" in ISS, f"dark large wizard image {pct}% not referenced")
        require(f"wizard-small-dark-{pct}.png" in ISS, f"dark small wizard image {pct}% not referenced")
        require(f"{pct}: " in BITMAPS, f"wizard image scale {pct}% not generated")
    require("from app_icon import" in BITMAPS, "wizard images are not drawn from the app icon")


def test_setup_icon_is_the_app_icon() -> None:
    require("from app_icon import" in ICON and "render_app_icon" in ICON,
            "uoink.ico is not generated from the app icon")
    require("logo-mark-color" not in ICON.split('"""', 2)[2], "uoink.ico still reads the old rust-U PNG")


def main() -> int:
    test_post_install_verification_does_not_spawn_ui()
    test_finish_launch_starts_helper_without_dashboard()
    test_welcome_page_is_dpi_safe()
    test_next_button_caption_is_never_restored_from_initialize_wizard()
    test_one_click_install_skips_pages_unless_customize_is_ticked()
    test_isolated_welcome_button_says_next()
    test_installer_copy_avoids_old_and_banned_words()
    test_verify_script_is_files_only_by_default()
    test_first_run_splash_suppresses_ready_toast()
    test_wizard_bitmaps_are_multi_scale()
    test_setup_icon_is_the_app_icon()
    print("ALL U-11 INSTALLER OVERHAUL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
