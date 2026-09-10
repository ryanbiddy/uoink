import ast,hashlib,json,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1];src=r/'_scratch/run_installed_decoders05_v3.py';out=r/'_scratch/run_installed_decoders.py'
s=src.read_text(encoding='utf8')
changes={
'import datetime as dt,hashlib,json,os,subprocess':'import argparse,datetime as dt,hashlib,json,os,subprocess',
'r=Path(__file__).resolve().parents[1]':"r=Path(__file__).resolve().parent\np=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);args=p.parse_args()",
"root=Path(r'E:\\AI\\projects\\uoink\\installation-receipts\\Agent Install 05');app=root/'app'":"root=args.root.resolve();assert root.is_relative_to(Path(r'E:\\AI\\projects\\uoink\\installation-receipts'));app=root/'app'",
"str(r/'_scratch'/script)":"str(r/script)",
"('installed_codec_probe05.py','codec-probe-02')":"('installed_codec_probe.py','codec-probe-02')",
}
for old,new in changes.items():
 assert s.count(old)==1,old;s=s.replace(old,new)
ast.parse(s)
with out.open('x',encoding='utf8',newline='\n') as f:f.write(s)
help_run=subprocess.run([sys.executable,'-I','-S','-B',str(out),'--help'],capture_output=True,text=True)
assert help_run.returncode==0 and '--root' in help_run.stdout
(r/'_scratch/portable-decoder-observer-review.json').write_text(json.dumps({'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'portable_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'changes':changes,'help_exit':help_run.returncode,'review':'Only explicit receipt root and portable bundle-relative input locations changed. Original startup restore, subprocess guards and expected behavior unchanged. Parse/help checked; actual decoding evidence is the original installed v3 observation, not a second executed claim.'},indent=2)+'\n',encoding='utf8')
