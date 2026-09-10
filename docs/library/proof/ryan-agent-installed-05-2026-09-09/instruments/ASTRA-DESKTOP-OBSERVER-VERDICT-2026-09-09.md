# Desktop observation supplement verdict

Approve this exact observer supplement for package-05's already prepared Agent
Install 05 session. The original driver refused the OneDrive Desktop during its
baseline, before Setup started. This is an observer limitation; no installation
failure or product repair is claimed. The original failure remains recorded.

The patch changes only how a reparse Desktop is observed and adds actual saved
task settings. It does not traverse that Desktop or hash its contents. Its
directory metadata must remain unchanged. All other path guards remain in force,
including application, data, package, Start Menu and Startup checks. Regular
Desktop directories retain their original shortcut inspection.

Both desktop-icon entries in the compiled installer require the desktopicon
task. The existing empty TASKS selection remains. SAVEINF records the actual
selection; exactly one empty Tasks value is required after each stage. Review
the actual Inno log for desktop icon creation too. These settings are documented
in [Inno Setup's command reference](https://jrsoftware.org/ishelp/topic_setupcmdline.htm).
The resulting claim is no selected desktop task, not unchanged cloud file bytes.

The copied supplement parses with zero errors. Six independent decision cases
pass, including refusal to exempt a reparse Start Menu or Desktop child. Exact
guard functions and the complete installed-marker, registry ownership and four
shortcut verification tail match the original after line-ending normalization.
All required launch suppression and isolation arguments remain. The first
validation failed on CRLF-versus-LF comparison only; its result and the exact
instrument repair are retained separately. No acceptance test changed.

Execution is limited to the sealed 95123073 package, non-elevated same-account
installation under the dedicated outside-checkout receipt root. No ordinary
profile, helper, credentials or cloud file content is accessed by this exemption.
Setup exit, selected settings, registry/shortcut observations and subsequent
installed checks must be recorded as observed. This review supplies permission
to execute the authorized check, not installed acceptance in advance.

Reviewed supplement SHA256:
8f05dd4754ee4b019aa2a8db8dc9031dfbc1848bd0a2c445b4f6852105935af2.
Source and original-refusal receipt: desktop-observer05-source.json.
Independent validation: desktop-observer05-validation.json.
