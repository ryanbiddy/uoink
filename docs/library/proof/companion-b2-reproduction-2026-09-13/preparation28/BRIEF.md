# Private Python 3.13 wheel reproduction proposal — 2026-09-13

Prepare only. Root reviews the sealed source before either command below runs.
The first Python 3.14 build succeeded with actual child/outer exits 0 and a
1,387,859-byte wheel, SHA-256
`d64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883`.
This proposal tests reproduction of that package; it does not qualify a model
stack, installation or market release.

The `copy` command, under reviewed Python 3.14.6 with `-I -S -B`, reads only the
33 exact retained stdlib runtime files in the prior sealed plan. It verifies
their names, sizes and hashes, uses capped reads with handle/path identity
checks, rejects links and reparse paths, and writes them exclusively to fresh
`_scratch/b2-stdlib313-runtime01`. It writes a private 16-byte `python313._pth`
containing only `python313.zip` and `.`, verifies the complete destination,
and retains a copy receipt separately. No original runtime configuration is
changed and no interpreter is launched by `copy`.

The separate `build` command re-verifies every preparation and private runtime
byte, including the absence of unlisted files. It launches only the fresh
private `python.exe`, never the original graph or staging interpreter. Before
wheel access the child requires Python 3.13.15, isolated/no-site/no-bytecode
flags, `site` absent, the exact private executable and exactly two private
stdlib search paths. The child retains the reviewed import/network/process/
ctypes/file guard, exact builder `ef718918…b4c3f`, and four unchanged recipe
inputs. Outputs use fresh `_scratch/b2-real-wheel-py313-01`; ambient epoch is
`2000000000`, compared with `1` for the Python 3.14 run.

The child reads the exact upstream wheel, copies it under the expected filename,
and performs the same opaque ZIP transformation and all 16 member/RECORD checks.
The bundled model asset is decompressed only as package bytes, hashed and
preserved; no model parser, tokenizer, package module, converter or inference
engine runs. It then reads the exact first output wheel and requires byte
equality. Preserve actual exits, raw console, startup paths, input identities,
guard results and comparison. A failure needs a repair brief and fresh label;
these fixed labels refuse reuse.

After root pins the new preparation seal externally, proposed commands are:

```powershell
C:\Python314\python.exe -I -S -B _scratch\b2-python313-reproduction-preparation01\copy-and-launch.py copy --manifest-sha256 <reviewed-seal-sha256> --execute-reviewed-action
C:\Python314\python.exe -I -S -B _scratch\b2-python313-reproduction-preparation01\copy-and-launch.py build --manifest-sha256 <reviewed-seal-sha256> --execute-reviewed-action
```

No runtime copy, private interpreter launch, wheel read or build happens during
preparation. The retained runtime hashes bind local bytes without establishing
new publisher provenance. Inputs and outputs must be quiescent: bounded reads
and observed identity checks do not defeat every hostile same-user mutation.
No dependency/pin/test/staging edits, installation, downloads, providers or
model execution are in scope. Earlier seals remain unchanged.
