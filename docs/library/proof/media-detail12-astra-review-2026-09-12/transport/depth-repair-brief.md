# Explicit saved-JSON depth bound

astra-media12-repair-worker01 has 56 passes and one failure. A 1,500-level
synthetic document parsed under this process and was returned as success after
field filtering. Catching RecursionError alone is not a depth contract. Add an
iterative maximum of 64 container levels before filtering, while retaining the
2 MiB byte cap and the existing exception handling. Keep all assertions. Then
run the unchanged 57-case union under fresh astra-media12-repair-worker02.
