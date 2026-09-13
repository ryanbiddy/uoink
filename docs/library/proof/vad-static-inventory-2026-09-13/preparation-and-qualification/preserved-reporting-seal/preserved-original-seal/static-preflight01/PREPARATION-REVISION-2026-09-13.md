# Preparation revision before static-preflight01

The first brief and reader bytes were copied to `draft01` and hashed before any
revision or execution. The reader is unchanged for this first synthetic check.

The brief now records the integrator's ruling that bounded, read-only artifact
inventory is already authorized. It requires isolated stdlib startup with
`-I -S -B`, explains argument/occupied-receipt exit behavior, and states the
limit of observed path checks against concurrent filesystem changes. It also
records the newly authorized synthetic parser checks. These changes narrow the
claims and remove an unnecessary request for Ryan's permission.

`qualify_parser.py` imports definitions from the proposed reader, disables its
`inspect` and `main`, and blocks the checkpoint path in a Python open audit
hook. All containers are generated in memory, all pickle payloads are literal
byte strings, and no pickle is executed. It tests successful metadata parsing
and specific refusal reasons, including an intentionally underreported deflate
payload. It emits structured case results; the caller must separately retain
the real process exit. No actual checkpoint read is authorized for this helper.

No product or frozen test is changed. A failure remains a failure until a
documented reader or synthetic-setup repair receives a fresh run label.
