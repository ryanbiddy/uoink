2026-09-14 — unexecuted draft correction

The first engine driver draft checked liveness when retaining the model, then called model.prepare() and immediately started the pipeline constructor. Reentrant revocation during model.prepare() could therefore admit another generated constructor before the later retention check refused it. Add the fixed owner liveness/identity check between those calls.

Move the driver's error capture outside the owner-operation context as well. This retains the first exception on the engine attempt if the context's final publication check raises. Constructor, returned-object and final identity requirements are otherwise unchanged.

The before files preserve this unexecuted draft. No test, constructor or Python startup occurred. This is a source-design correction, not a repaired test result.
