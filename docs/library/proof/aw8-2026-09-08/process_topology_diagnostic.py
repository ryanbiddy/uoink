import json
import subprocess
from pathlib import Path
import sys
import library_mirror as mirror
from tests.test_phase4_av5m4b_lifetime import _prove_real_child_stall

def test_observe_redirector_and_failed_stall(tmp_path):
    session=mirror._VaultIoSession.start(str(tmp_path))
    record={"interpreter":sys.executable,"session_pid":session.pid}
    try:
        command="Get-CimInstance Win32_Process -Filter \"ParentProcessId = %d\" | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress" % session.pid
        result=subprocess.run(["pwsh","-NoProfile","-Command",command],capture_output=True,text=True,check=True)
        record["children"]=json.loads(result.stdout) if result.stdout.strip() else []
        try: record["stall"]=_prove_real_child_stall(session)
        except AssertionError as exc: record["failed_stall"]=exc.args[0]
        print(json.dumps(record,ensure_ascii=True))
        Path(__file__).with_name("aw8-process-topology.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
    finally:
        assert session.terminate()
