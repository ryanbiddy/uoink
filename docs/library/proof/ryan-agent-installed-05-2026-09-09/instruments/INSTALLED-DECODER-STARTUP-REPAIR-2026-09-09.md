# Installed decoder observation repair

The first launcher exited one before a subprocess because a copied Windows
environment dict used uppercase keys. That exact repair is retained separately.
The second launcher started the installed interpreter and exited one at the
probe's no-site assertion, before decoder imports. Its output stays failed.

The actual installed python313._pth explicitly contains import site. A flags-only
observation confirms isolated=1 and no_site=0 despite -I -S. Python's Windows
documentation describes this explicit ._pth opt-in. This is a startup condition
of the instrument, not an observed decoder defect.

Approve the v3 launcher supplement for these two unchanged probes. It temporarily
comments only that exact import-site line in the dedicated installed test app,
records original/observation hashes, and restores the original bytes in finally.
Both original probe assertions and network/process/database guards stay intact.
Use fresh output/environment paths and preserve the failed first probe. No other
installed helper runs concurrently. The complete installed-file comparison has
already passed all 32,054 destinations. Verify restoration afterward before C22.

This is an instrumented decoder compatibility check, not ordinary startup or
unmodified-app behavior evidence. C22 separately exercises installed startup with
its original reviewed guards. No build source, acceptance test, or shipping
package changes. Review found the bounded mutation, fresh paths, subprocess
timeout and finally restoration explicit in v3. Proceed under the approved
installation-observation scope.

Reference: https://docs.python.org/3.13/using/windows.html#finding-modules
