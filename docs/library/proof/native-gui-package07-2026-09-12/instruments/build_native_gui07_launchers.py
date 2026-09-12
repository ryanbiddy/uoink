"""Compile fixed local launchers so Sky can launch with the reviewed isolation driver."""
import hashlib,json,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07\native-gui01')
compiler=Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
pythonw=Path(sys.executable).with_name('pythonw.exe');assert pythonw.is_file()
driver=repo/'_scratch/native_gui07_driver.py'
compile(driver.read_text(encoding='utf8'),str(driver),'exec')
for mode in ('dashboard','desktop'):
 argv=subprocess.list2cmdline(['-I','-S','-B',str(driver),mode])
 literal=lambda s:'@"'+str(s).replace('"','""')+'"'
 source='using System; using System.Diagnostics; class NativeGui { [STAThread] static void Main() { var p=new ProcessStartInfo(); p.FileName='+literal(pythonw)+'; p.Arguments='+literal(argv)+'; p.UseShellExecute=false; p.CreateNoWindow=true; p.WorkingDirectory='+literal(root)+'; Process.Start(p); } }'
 cs=root/('Launch-'+mode+'.cs');exe=root/('Launch-'+mode+'.exe')
 assert not cs.exists() and not exe.exists();cs.write_text(source,encoding='utf8')
 result=subprocess.run([str(compiler),'/nologo','/target:winexe','/out:'+str(exe),str(cs)],capture_output=True,text=True)
 (root/('compile-'+mode+'.json')).write_text(json.dumps({'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),'cs_sha256':hashlib.sha256(cs.read_bytes()).hexdigest(),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest() if exe.exists() else None},indent=2)+'\n')
 assert result.returncode==0,result.stdout
 print(exe)
