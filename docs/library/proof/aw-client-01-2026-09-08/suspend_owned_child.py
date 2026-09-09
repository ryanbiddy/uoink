import ctypes, ctypes.wintypes as w, datetime as dt, json, os, time
from pathlib import Path

root=Path(__file__).resolve().parent
pid=71588
assert root.name=='aw-client-01'
events=[json.loads(x) for x in (root/'records/stdio-62820/events.jsonl').read_text(encoding='utf-8').splitlines()]
assert any(x['kind']=='child_started' and x['child_pid']==pid for x in events)
assert not any(x['kind']=='child_exit' for x in events)
k=ctypes.WinDLL('kernel32',use_last_error=True)
n=ctypes.WinDLL('ntdll')
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
k.CloseHandle.argtypes=[w.HANDLE]
n.NtSuspendProcess.argtypes=[w.HANDLE];n.NtSuspendProcess.restype=w.LONG
n.NtResumeProcess.argtypes=[w.HANDLE];n.NtResumeProcess.restype=w.LONG
h=k.OpenProcess(0x0800|0x1000,False,pid)
if not h:raise ctypes.WinError(ctypes.get_last_error())
buf=ctypes.create_unicode_buffer(32768);size=w.DWORD(len(buf))
if not k.QueryFullProcessImageNameW(h,0,buf,ctypes.byref(size)):raise ctypes.WinError(ctypes.get_last_error())
assert Path(buf.value)==Path(r'C:\Python314\python.exe')
def log(kind,**fields):
 record={'kind':kind,'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'monotonic_ns':time.perf_counter_ns(),'guard_pid':os.getpid(),'child_pid':pid,'image':buf.value,**fields}
 with (root/'transport-suspend-events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
 print(json.dumps(record),flush=True)
suspended=False
try:
 status=n.NtSuspendProcess(h);log('suspend',ntstatus=status)
 if status!=0:raise RuntimeError('Suspend failed')
 suspended=True
 end=time.monotonic()+90
 while time.monotonic()<end and not (root/'resume-child.signal').exists():time.sleep(.1)
finally:
 if suspended:log('resume',ntstatus=n.NtResumeProcess(h),release_signal=(root/'resume-child.signal').exists())
 k.CloseHandle(h)
