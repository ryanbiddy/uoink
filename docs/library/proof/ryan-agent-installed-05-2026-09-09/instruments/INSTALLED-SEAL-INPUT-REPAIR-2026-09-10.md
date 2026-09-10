# Installed evidence seal input correction

The first export stopped before sealing because its copy boundary received a
relative summary path. The summary was inside the approved scratch directory,
but the copier correctly required an absolute contained path. No receipt or
test result changed. The partial export has no SHA256 manifest and is retained.

Use the absolute summary path and a fresh export directory. Keep the same source
observations, summary and containment assertion. Include this note and the first
export's traceback. A new export is packaging evidence, not a measurement rerun.
