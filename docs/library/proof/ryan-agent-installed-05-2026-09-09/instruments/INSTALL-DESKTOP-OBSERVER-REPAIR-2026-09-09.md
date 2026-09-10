# Installation observer repair: OneDrive Desktop

The original reviewed driver exited one before Setup when its ordinary-shortcut
snapshot rejected C:\Users\hello\OneDrive\Desktop as a reparse directory.
No app directory, install.json, Inno log or Setup process was created. Preserve
the failed invocation. The installer package and product source are unchanged.

Prepare a separate, exact-diff observer supplement. Keep every app, profile,
package, Start Menu and Startup path guard. Only the ordinary Desktop may be
recorded without traversing a reparse entry: retain its directory metadata hash,
mark contents unobserved, and compare the metadata before/after. Do not hydrate
cloud files or claim their shortcut contents were hashed. Regular desktops keep
the original inspection. A different reparse path still causes refusal.

Both compiled desktop-icon entries require the desktopicon task. The command
already selects no tasks. Add SAVEINF to retain actual selected settings and
require exactly one empty Tasks entry after Setup/reinstall. Review actual Inno
logs for any desktop icon creation as well. Official command documentation:
https://jrsoftware.org/ishelp/topic_setupcmdline.htm . This is an observation
supplement, not a product/test fixture change or a waiver of an OS safety barrier.

Before execution, verify the exact patch, parse PowerShell, and independently
exercise the supplement's Desktop decision function against regular Desktop,
reparse Desktop, regular Start Menu and reparse Start Menu cases. Require the
existing full driver guards, argv and four-shortcut checks to remain in the
copied script. Then use the already prepared Agent Install 05 profiles, since
the first command never started Setup. Preserve actual exits and failures.
