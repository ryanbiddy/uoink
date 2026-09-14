# Root passive checker correction

Passive receipt check df6c0c failed before completing its source/control loop.
The new checker added source.name == original['name'], but the reviewed launcher
intentionally copies ROOT-ADMISSION-cancel.json as ROOT-ADMISSION.json. That
alias is present in the fixed source and before receipt. This is a root checker
error; it does not change native observation a9321b or its recorded exit 0.

Preserve check-native-runtime-owner-cancel01.py and its exact failed tool object.
Create a separate 02 checker that permits only the fixed admission alias and
otherwise retains exact name equality. All source/hash, guard, owner, native
exit and journal-frame checks remain. Invoke that passive derivative once on
the existing fixed text receipts. No candidate, native process, physical journal,
fixture, support file, checkpoint or D2 output is rerun or reopened.
