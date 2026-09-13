# Qualification import setup repair

`converter-preflight01` exited 1 during the initial `import zip_bounds`. The fail-closed file audit rejected an import-loader read outside the five allowlisted copied inputs. It stopped before the case loop; no synthetic case results were produced. Preserve its empty stdout, traceback, plan, exit receipt and five source copies. Do not call it an 82-case failure or a converter/model result.

For a fresh `converter-preflight02`, load only the already-read, hash-recorded source bytes of `zip_bounds.py` and `fixed_converter.py` into ordinary named modules. Compile and execute those two reviewed converter implementation modules as required for synthetic testing; never compile the retained reference reader, a checkpoint string or model source. This avoids import-loader secondary filesystem requests while keeping the same audit allowlist. Register each implementation module before execution so dataclass type metadata works normally.

The converter, ZIP functions, fixed plan and every behavior assertion remain unchanged. Only the synthetic harness module-loading setup changes; the real profile remains absent and no artifact file is accessed.
