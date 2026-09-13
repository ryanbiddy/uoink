"""Generated D1 wrapper fixture. Never imports or executes any D1 source."""
import json
import os
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("D1_WRAPPER_SYNTHETIC_SCOPE") == "uoink-d1-wrapper-fixture-v1"
selected = os.environ.get("D1_WRAPPER_SYNTHETIC_EXIT")
assert selected in ("0", "1", "2", "3")
preloaded = set(sys.modules)


def guard(event, args):
    if event == "open" or event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        raise RuntimeError("Inert child has no filesystem or process capability")
    if event == "import" and args[0] not in preloaded:
        raise RuntimeError("Inert child has no further imports")


sys.addaudithook(guard)
print(json.dumps({"scope": "uoink-d1-wrapper-fixture-v1", "requested_exit": int(selected),
                  "startup_binding_asserted": True, "isolated": True,
                  "no_site": True, "no_bytecode": True, "d1_source_executed": False}))
sys.exit(int(selected))
