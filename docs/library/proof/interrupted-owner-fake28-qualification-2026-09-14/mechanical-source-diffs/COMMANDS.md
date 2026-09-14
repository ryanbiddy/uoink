# Mechanical commands

The data-only prepare_copies01.ps1 bound and copied the three fixed original/derivative pairs. The original paths come from S02, S04 and S09 in repair02/INPUTS.json; complete bindings are retained in SOURCE-BINDINGS.json.

For each of durable_lifecycle.py, generated_adapter_flow.py and generated_journal_setup.py, from this package directory, the raw diff invocation was:

```
git --no-pager -c core.autocrlf=false diff --no-index --binary --no-ext-diff --no-textconv -- original/NAME candidate/NAME
```

PowerShell 7.6.5 native stdout redirection wrote patches/NAME.patch. The caller disabled PSNativeCommandUseErrorActionPreference, reset global LASTEXITCODE before the command, captured it immediately afterward and exited with that integer. All three actual outer returns are retained with exit 1.

From the checkout root, each raw patch was checked and then applied with:

```
git -c core.autocrlf=false apply --check --whitespace=nowarn -p2 --directory=_scratch/interrupted-repair02-mechanical-diffs01/reconstruction/forward -- _scratch/interrupted-repair02-mechanical-diffs01/patches/NAME.patch
git -c core.autocrlf=false apply --whitespace=nowarn -p2 --directory=_scratch/interrupted-repair02-mechanical-diffs01/reconstruction/forward -- _scratch/interrupted-repair02-mechanical-diffs01/patches/NAME.patch
```

The reverse copies used the same two invocations with --reverse and the reconstruction/reverse directory. Each of these 12 actual returns is retained separately. No --index, --cached, --unsafe-paths, whitespace-fixing option or source-path application was used. verify_bytes01.ps1 then compared complete reconstructed and external-source byte hashes and removed only the verified disposable copies.
