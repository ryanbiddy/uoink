"""Two fixed cached-wheel byte inspections; never extract/import their members."""
from __future__ import annotations
import base64
import csv
import email.parser
import email.policy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time
import zipfile

BASE=Path(__file__).absolute().parent
ROOT=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\python313-graph-01\cache\wheels')
SPECS=(
    {'name':'antlr4-python3-runtime','version':'4.9.3','module':'antlr4','dist':'antlr4_python3_runtime-4.9.3.dist-info',
     'relative':'d5/b3/74/a35b66048c9de6631cd74cbc9475e6feb3e69a467983446bd8/antlr4_python3_runtime-4.9.3-py3-none-any.whl',
     'bytes':144613,'sha256':'d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37'},
    {'name':'proxy-tools','version':'0.1.0','module':'proxy_tools','dist':'proxy_tools-0.1.0.dist-info',
     'relative':'1b/86/84/a8355e4f91698784a475f3eb40500d31a57c528e3217758043/proxy_tools-0.1.0-py3-none-any.whl',
     'bytes':2943,'sha256':'a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68'},
)
START=time.monotonic()
def need(value,message):
    if not value: raise ValueError(message)
def clock(): need(time.monotonic()-START<=30,'Cooperative 30-second deadline')
def digest(raw): return hashlib.sha256(raw).hexdigest()
def identity(info):
    fields={name:getattr(info,name) for name in ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
    if hasattr(info,'st_birthtime_ns'): fields['st_birthtime_ns']=info.st_birthtime_ns
    return fields
def chain(path):
    for item in reversed((path,)+tuple(path.parents)):
        try: info=item.lstat()
        except FileNotFoundError: continue
        need(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'Observed link/reparse path')
        if item!=path: need(stat.S_ISDIR(info.st_mode),'Nondirectory ancestor')
def read(path,cap):
    clock();chain(path);before=path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size<=cap,'Input type/size bound')
    with path.open('rb') as stream:
        handle_before=os.fstat(stream.fileno());raw=stream.read(cap+1);handle_after=os.fstat(stream.fileno())
    after=path.lstat()
    need(len(raw)<=cap and identity(before)==identity(after) and identity(handle_before)==identity(handle_after),'Read changed within one identity API')
    left,right=identity(before),identity(handle_before)
    if os.name=='nt':
        need('st_birthtime_ns' in left and 'st_birthtime_ns' in right,'Required Windows birthtime absent')
        left.pop('st_ctime_ns');right.pop('st_ctime_ns')
    need(left==right,'Path/handle identity differs')
    return raw,identity(before),identity(handle_before)

need(len(sys.argv)==2 and re.fullmatch('[0-9a-f]{64}',sys.argv[1]),'Exact preparation hash argument required')
need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'Isolated startup required')
need(os.environ.get('IG_FORBIDDEN_LIVE')==r'C:\Users\hello\AppData\Local\Uoink\index.db','Lexical startup binding absent')
need(os.environ.get('TORCH_DEVICE_BACKEND_AUTOLOAD')=='0','Backend autoload must be disabled')
manifest_path=BASE/'PREPARATION-HASHES.json'
manifest_raw,_,_=read(manifest_path,131072)
need(digest(manifest_raw)==sys.argv[1],'Preparation hash differs')
rows=json.loads(manifest_raw)
need(type(rows) is list and 8<len(rows)<30,'Preparation membership bound')
sources={};input_identities={}
for row in rows:
    name=row['path']
    need(type(name) is str and re.fullmatch(r'[A-Za-z0-9_./+\-]+',name) and not name.startswith('/') and all(p not in {'','.','..'} for p in name.split('/')),'Noncanonical source path')
    need(name not in sources,'Duplicate preparation path')
    raw,ident,_=read(BASE/name,4194304)
    need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],'Preparation input differs')
    sources[name]=raw;input_identities[name]=ident
need(not any(n.split('.')[0] in {'torch','whisperx','ctranslate2','faster_whisper','numpy','nltk'} for n in sys.modules),'Unexpected model/package preload')
output=BASE/'inspection01.json'
allowed_reads={os.path.normcase(os.path.abspath(str(BASE/name))) for name in sources}|{os.path.normcase(str(manifest_path))}|{os.path.normcase(os.path.abspath(str(ROOT/spec['relative']))) for spec in SPECS}
output_name=os.path.normcase(os.path.abspath(str(output)));violations=[]
def audit(event,args):
    if event=='open':
        path,mode,flags=args
        name=os.path.normcase(os.path.abspath(os.fsdecode(path))) if isinstance(path,(str,bytes,os.PathLike)) else ''
        writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
        if name not in ({output_name} if writing else allowed_reads): violations.append(event);raise PermissionError('Unapproved content path')
    elif event.startswith(('socket.','subprocess.','ctypes.','winreg.')) or event in {'os.system','os.startfile','os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chdir','os.truncate','os.chmod','os.utime','os.mkdir'}:
        violations.append(event);raise PermissionError('Unapproved side effect')
sys.addaudithook(audit)

def inspect(spec):
    path=ROOT/spec['relative'];blob,path_id,handle_id=read(path,spec['bytes'])
    need(len(blob)==spec['bytes'] and digest(blob)==spec['sha256'],'Historical wheel pin mismatch')
    need(len(blob)>=22 and blob[-22:-18]==b'PK\x05\x06','Exact no-comment EOCD required')
    signature,disk,cd_disk,n_disk,n_total,cd_size,cd_offset,comment=struct.unpack('<4s4H2IH',blob[-22:])
    need(disk==cd_disk==comment==0 and n_disk==n_total and 1<=n_total<=1000 and cd_offset+cd_size==len(blob)-22,'ZIP directory bounds')
    payloads={};inventory=[];cursor=0;expanded=0
    with zipfile.ZipFile(io.BytesIO(blob),'r') as archive:
        entries=archive.infolist();need(len(entries)==n_total and archive.start_dir==cd_offset and not archive.comment,'ZIP count/offset mismatch')
        folded=set()
        for entry in entries:
            clock();name=entry.filename
            need(re.fullmatch(r'[A-Za-z0-9_./+\-]+',name) and not name.startswith('/') and all(p not in {'','.','..'} for p in name.split('/')),'Unsafe member name')
            need(name.casefold() not in folded and not entry.is_dir(),'Duplicate/case-alias/directory member');folded.add(name.casefold())
            mode=entry.external_attr>>16
            need(stat.S_IFMT(mode) in (0,stat.S_IFREG) and not entry.external_attr&0x10,'Nonregular member')
            need(entry.compress_type in (0,8) and entry.flag_bits&~0x800==0 and not entry.extra and not entry.comment,'ZIP compression/flags/extra profile')
            need(0<=entry.file_size<=262144 and entry.header_offset==cursor,'Member size/extent profile')
            need(name.startswith(spec['module']+'/') or name.startswith(spec['dist']+'/'),'Unexpected package root')
            if name.startswith(spec['module']+'/'): need(name.endswith('.py'),'Unexpected package payload type')
            need(not name.lower().endswith(('.pth','.dll','.pyd','.exe','.so','.dylib')),'Executable/native installation payload')
            local=struct.unpack('<4s5H3I2H',blob[cursor:cursor+30])
            need(local[0]==b'PK\x03\x04' and local[2]==entry.flag_bits and local[3]==entry.compress_type and local[6]==entry.CRC and local[7]==entry.compress_size and local[8]==entry.file_size and local[10]==0,'Local/central header mismatch')
            end_name=cursor+30+local[9];data_end=end_name+entry.compress_size
            need(blob[cursor+30:end_name]==name.encode('ascii') and data_end<=cd_offset,'Member name/data bounds')
            with archive.open(entry) as stream: raw=stream.read(262145)
            need(len(raw)==entry.file_size and len(raw)<=262144,'Expanded member size mismatch')
            expanded+=len(raw);need(expanded<=8388608,'Expanded wheel total bound')
            payloads[name]=raw;inventory.append({'path':name,'bytes':len(raw),'sha256':digest(raw),'crc32':f'{entry.CRC:08x}','compression':entry.compress_type})
            cursor=data_end
        need(cursor==cd_offset,'Gap/overlap before central directory')
    dist=spec['dist'];required={dist+'/'+name for name in ('METADATA','WHEEL','RECORD')}
    need(required<=payloads.keys(),'Required wheel metadata absent')
    record_path=dist+'/RECORD';record_rows=list(csv.reader(io.StringIO(payloads[record_path].decode('utf-8'),newline='')))
    recorded=set()
    for row in record_rows:
        need(len(row)==3 and row[0] in payloads and row[0] not in recorded,'RECORD membership/duplicate mismatch')
        name,hash_field,size=row;recorded.add(name)
        if name==record_path: need(hash_field==size=='','RECORD self row must be blank')
        else:
            expected='sha256='+base64.urlsafe_b64encode(hashlib.sha256(payloads[name]).digest()).rstrip(b'=').decode('ascii')
            need(hash_field==expected and size==str(len(payloads[name])),'RECORD payload hash/size mismatch')
    need(recorded==payloads.keys(),'Incomplete RECORD membership')
    metadata=email.parser.BytesParser(policy=email.policy.compat32).parsebytes(payloads[dist+'/METADATA'])
    wheel=email.parser.BytesParser(policy=email.policy.compat32).parsebytes(payloads[dist+'/WHEEL'])
    normalize=lambda name: re.sub(r'[-_.]+','-',name).lower()
    need(len(metadata.get_all('Name',[]))==len(metadata.get_all('Version',[]))==1 and normalize(metadata['Name'])==spec['name'] and metadata['Version']==spec['version'],'Exact package metadata identity differs')
    need(wheel.get_all('Root-Is-Purelib')==['true'] and wheel.get_all('Tag')==['py3-none-any'],'Wheel purity/tag differs')
    selected={name:raw.decode('utf-8') for name,raw in payloads.items() if name in required or (name.startswith(dist+'/') and ('license' in name.casefold() or 'copying' in name.casefold() or name.endswith('/NOTICE')))}
    licenses=[name for name in selected if name not in required]
    need(identity(path.lstat())==path_id,'Wheel identity changed after inspection')
    return {'package':spec['name'],'version':spec['version'],'path':str(path),'bytes':len(blob),'sha256':digest(blob),'historical_pin_matched':True,'artifact_verified_in_this_invocation':True,'public_release_record':False,'public_wheel_url':None,'member_count':len(inventory),'expanded_bytes':expanded,'record_members_verified':len(recorded),'inventory':inventory,'selected_text':selected,'license_text_members':licenses,'license_text_missing':not licenses,'metadata_license_claim':metadata.get_all('License',[]),'requires_python':metadata.get_all('Requires-Python',[]),'requires_dist':metadata.get_all('Requires-Dist',[]),'path_identity':path_id,'handle_identity':handle_id,'provenance_limit':'Historical pip log/origin claims were retained; matching bytes do not authenticate a publisher or reproduce the build.'}

results=[];error=None
try:
    for spec in SPECS: results.append(inspect(spec))
except Exception as exc:
    error={'type':type(exc).__name__,'message':str(exc)}
post=[]
try:
    for row in rows:
        raw,ident,_=read(BASE/row['path'],4194304)
        need(raw==sources[row['path']] and ident==input_identities[row['path']],'Preparation changed after inspection')
        post.append({'path':row['path'],'bytes':len(raw),'sha256':digest(raw)})
    need(read(manifest_path,131072)[0]==manifest_raw,'Preparation manifest changed')
    for result in results: need(identity(Path(result['path']).lstat())==result['path_identity'],'Inspected wheel changed before final receipt')
    need(not violations,'Audit violation');clock()
except Exception as exc:
    error={'type':type(exc).__name__,'message':str(exc),'stage':'postcheck','earlier_error':error}
exit_code=0 if error is None and len(results)==2 else 2
receipt={'inspection_status':'VALID' if exit_code==0 else 'REFUSED','exit':exit_code,'scope':'Existing two wheel bytes only; no extraction, member import, execution, fetch, build or install. Missing license text is a separate reported finding.','results':results,'error':error,'preparation_sha256':sys.argv[1],'source_hashes_after':post,'guard':{'startup_binding':True,'violations':violations},'elapsed_seconds':time.monotonic()-START}
raw=json.dumps(receipt,indent=2).encode()+b'\n'
need(len(raw)<=262144,'Final receipt bound')
clock()
chain(output)
with output.open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
print(json.dumps({'status':receipt['inspection_status'],'inspected':len(results),'exit':exit_code,'elapsed_seconds':receipt['elapsed_seconds']}))
raise SystemExit(exit_code)
