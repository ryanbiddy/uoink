"""Prepared synthetic qualification; execute only after exact root admission."""
import ast
from contextlib import contextmanager
import dataclasses
import encodings.utf_8_sig
import hashlib
import inspect
import json
import math
import ntpath
import os
from pathlib import Path
import re
import struct
import sys
import time
import types
import typing

HERE = Path(__file__).absolute().parent
FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'
assert os.environ.get('IG_FORBIDDEN_LIVE') == FORBIDDEN
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
NAMES = ('plain_state_reader.py', 'qualify_reader.py', 'fixed-plan.json', 'INPUTS.json')
READS = {ntpath.normcase(str(HERE/name)) for name in NAMES}
HEAVY = {'torch', 'torchaudio', 'whisperx', 'whisper', 'faster_whisper', 'ctranslate2',
    'pyannote', 'transformers', 'tokenizers', 'safetensors', 'numpy', 'huggingface_hub'}
PRELOADED = sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
assert not PRELOADED
ALLOWED_IMPORTS = set(sys.modules) | {'plain_state_reader'}
EVENTS = []

def deny(event):
    EVENTS.append(event)
    raise AssertionError('Synthetic reader guard denied '+event)

def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        if (not isinstance(path, (str, bytes, os.PathLike))
            or ntpath.normcase(ntpath.abspath(os.fsdecode(path))) not in READS
            or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            deny(event)
    elif event == 'import' and args[0] not in ALLOWED_IMPORTS:
        deny('import:'+str(args[0]))
    elif event.startswith(('socket.', 'subprocess.', 'ctypes.', 'winreg.')) or event in {
        'os.system', 'os.startfile', 'os.startfile/2', 'os.spawn', 'os.fork', 'os.exec',
        'os.add_dll_directory', 'os.listdir', 'os.scandir', 'os.mkdir', 'os.remove',
        'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.utime'}:
        deny(event)

LIVE_PARENT = ntpath.dirname(ntpath.normcase(FORBIDDEN))
ORIGINALS = {name:getattr(os,name) for name in ('stat','lstat','readlink')}
ORIGINAL_REALPATH = os.path.realpath
WRAPPERS = {}
def check_metadata(path):
    if isinstance(path,(str,bytes,os.PathLike)):
        text=os.fsdecode(path).replace('/', '\\')
        if text.startswith('\\\\?\\'):text=text[4:]
        elif text.startswith('\\??\\'):text=text[4:]
        name=ntpath.normcase(ntpath.abspath(text))
        if name == LIVE_PARENT or name.startswith(LIVE_PARENT+'\\'):
            deny('live metadata')
for name,original in ORIGINALS.items():
    def wrapper(path,*args,_original=original,**kwargs):
        check_metadata(path)
        return _original(path,*args,**kwargs)
    WRAPPERS[name]=wrapper
    setattr(os,name,wrapper)
def realpath_wrapper(path,*args,**kwargs):
    check_metadata(path)
    return ORIGINAL_REALPATH(path,*args,**kwargs)
os.path.realpath=realpath_wrapper
sys.addaudithook(audit)

raw_inputs={name:(HERE/name).read_bytes() for name in NAMES}
bindings=json.loads(raw_inputs['INPUTS.json'].decode('utf-8'))
for name in NAMES[:-1]:
    assert hashlib.sha256(raw_inputs[name]).hexdigest()==bindings['child_files'][name]
reader=types.ModuleType('plain_state_reader')
reader.__file__=str(HERE/'plain_state_reader.py')
sys.modules[reader.__name__]=reader
exec(compile(raw_inputs['plain_state_reader.py'],reader.__file__,'exec'),reader.__dict__)
assert hashlib.sha256(raw_inputs['fixed-plan.json']).hexdigest()==reader.PLAN_SHA256
plan=json.loads(raw_inputs['fixed-plan.json'].decode('utf-8-sig'))
ROWS=sorted(plan['rows'],key=lambda row:row['key'])
assert len(ROWS)==54
SCHEMA=tuple((row['key'],tuple(row['shape'])) for row in ROWS)
assert reader.FIXED_SHAPES==SCHEMA
assert sum(math.prod(row['shape']) for row in ROWS)==1_472_999
assert plan['total_output_data_bytes']==5_891_996

def encode_header(document):
    raw=json.dumps(document,ensure_ascii=True,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('utf-8')
    return raw+b' '*(-len(raw)%8)

DOCUMENT={}
parts=[]
cursor=0
for index,row in enumerate(ROWS):
    count=math.prod(row['shape']);size=count*4
    DOCUMENT[row['key']]={'dtype':'F32','shape':row['shape'][:],'data_offsets':[cursor,cursor+size]}
    marker=0x3F000000+index*512
    parts.append(struct.pack('<I',marker)*count)
    cursor+=size
DATA=b''.join(parts)
assert len(DATA)==5_891_996
HEADER=encode_header(DOCUMENT)
BASE=struct.pack('<Q',len(HEADER))+HEADER+DATA
EVIDENCE=hashlib.sha256(b'Only locally generated synthetic finite F32 fixtures; no real asset approval.').hexdigest()

def profile(raw, **changes):
    item=reader.ApprovalProfile('synthetic','synthetic:fixed-reader-v1',hashlib.sha256(raw).hexdigest(),
        len(raw),EVIDENCE,reader.PLAN_SHA256)
    return dataclasses.replace(item,**changes)

def read(raw=BASE, **changes):
    return reader.verify_bytes(raw,profile(raw,**changes))

def with_header(raw_header, data=DATA, *, pad=True):
    if pad:raw_header+=b' '*(-len(raw_header)%8)
    return struct.pack('<Q',len(raw_header))+raw_header+data

def changed_document(change):
    document={key:{'dtype':value['dtype'],'shape':value['shape'][:],
        'data_offsets':value['data_offsets'][:]} for key,value in DOCUMENT.items()}
    change(document)
    return with_header(encode_header(document))

def refuse(fn, fragment):
    try:fn()
    except reader.Refusal as error:
        assert fragment in str(error),(fragment,str(error))
        return
    raise AssertionError('Expected refusal: '+fragment)

@contextmanager
def patched(owner,name,value):
    original=getattr(owner,name)
    setattr(owner,name,value)
    try:yield
    finally:setattr(owner,name,original)

def bomb(*args,**kwargs):
    raise AssertionError('Forbidden interpretation seam reached')

CASES=[]
def case(name):
    def decorate(fn):CASES.append((name,fn));return fn
    return decorate
def parameter_case(name,fn):CASES.append((name,fn))

@case('canonical_full_schema_and_converter_plan_binding')
def canonical():
    result=read()
    assert result.snapshot is BASE
    assert len(result.tensors)==54 and result.data_start==8+len(HEADER)
    assert tuple((row.key,row.shape) for row in result.tensors)==SCHEMA
    assert sum(row.elements for row in result.tensors)==1_472_999
    expected_cursor=result.data_start
    for tensor in result.tensors:
        assert tensor.dtype=='F32' and tensor.start==expected_cursor
        view=result.tensor_bytes(tensor.key)
        assert view.readonly and bytes(view)==BASE[tensor.start:tensor.stop]
        assert len(view)==tensor.elements*4
        expected_cursor=tensor.stop
    assert expected_cursor==len(BASE)
    description=json.loads(result.description_json)
    assert description['tensor_count']==54 and description['dense_data_bytes']==5_891_996
    assert description['native_or_model_qualified'] is False and description['release_approved'] is False

@case('immutable_snapshot_descriptors_and_checked_slices')
def immutable():
    result=read()
    try:result.snapshot=b'changed'
    except dataclasses.FrozenInstanceError:pass
    else:raise AssertionError('Mutable state')
    try:result.tensors[0].start=0
    except dataclasses.FrozenInstanceError:pass
    else:raise AssertionError('Mutable descriptor')
    try:result.tensor_bytes(result.tensors[0].key)[0]=1
    except TypeError:pass
    else:raise AssertionError('Writable returned bytes')
    refuse(lambda:result.tensor_bytes('not-a-key'),'Unknown fixed tensor')
    refuse(lambda:result.tensor_bytes(1),'exact string')

@case('finite_signed_zero_subnormal_and_extreme_bits_preserved')
def finite_bits():
    bits=(0,0x80000000,1,0x80000001,0x007FFFFF,0x807FFFFF,0x00800000,
        0x80800000,0x7F7FFFFF,0xFF7FFFFF,0x3F800000,0xBF800000)
    block=b''.join(struct.pack('<I',word) for word in bits)
    data=(block*((len(DATA)+len(block)-1)//len(block)))[:len(DATA)]
    raw=with_header(HEADER,data)
    result=read(raw)
    assert result.snapshot is raw
    assert b''.join(bytes(result.tensor_bytes(item.key)) for item in result.tensors)==data
    assert tuple(word[0] for word in struct.iter_unpack('<I',data[:len(block)]))==bits

class BombSnapshot:
    __len__=__bytes__=__fspath__=__str__=bomb

@case('missing_approval_before_snapshot_or_interpretation')
def missing_approval():
    with patched(reader,'_header_document',bomb),patched(reader.hashlib,'sha256',bomb):
        refuse(lambda:reader.verify_bytes(BombSnapshot(),None),'Explicit approval')

@case('real_approval_absent_before_snapshot_or_interpretation')
def real_absent():
    item=dataclasses.replace(profile(BASE),purpose='real')
    with patched(reader,'_header_document',bomb),patched(reader.hashlib,'sha256',bomb):
        refuse(lambda:reader.verify_bytes(BombSnapshot(),item),'approval remains absent')
    assert reader.REAL_PROFILE is None

@case('synthetic_profile_cannot_authorize_original_checkpoint')
def original_refused():
    item=dataclasses.replace(profile(BASE),output_sha256=reader.ORIGINAL_SHA256)
    with patched(reader,'_header_document',bomb),patched(reader.hashlib,'sha256',bomb):
        refuse(lambda:reader.verify_bytes(BombSnapshot(),item),'cannot authorize original checkpoint')

@case('wrong_size_refused_before_hash_or_parse')
def size_first():
    item=dataclasses.replace(profile(BASE),output_size=len(BASE)-1)
    with patched(reader,'_header_document',bomb),patched(reader.hashlib,'sha256',bomb):
        refuse(lambda:reader.verify_bytes(BASE,item),'size mismatch')

@case('wrong_hash_refused_before_header_parse')
def hash_first():
    item=dataclasses.replace(profile(BASE),output_sha256='0'*64)
    with patched(reader,'_header_document',bomb):
        refuse(lambda:reader.verify_bytes(BASE,item),'SHA256 mismatch')

for label,value in [('bytearray',bytearray(BASE)),('memoryview',memoryview(BASE)),('path-string',FORBIDDEN)]:
    parameter_case('immutable_input_rejects_'+label,
        lambda value=value:refuse(lambda:reader.verify_bytes(value,profile(BASE)),'Immutable bounded bytes'))

for name,changes,fragment in [
    ('purpose-type',{'purpose':1},'approval remains absent'),
    ('purpose-unknown',{'purpose':'unknown'},'approval remains absent'),
    ('id-unbound',{'profile_id':'real:unknown'},'synthetic profile ID'),
    ('sha-upper',{'output_sha256':'A'*64},'digest field'),
    ('evidence-missing',{'evidence_sha256':''},'digest field'),
    ('plan-wrong',{'plan_sha256':'0'*64},'plan binding'),
    ('size-bool',{'output_size':True},'output size bound'),
    ('size-huge',{'output_size':10**100},'output size bound'),
    ('size-over-cap',{'output_size':reader.MAX_OUTPUT+1},'output size bound')]:
    parameter_case('profile_'+name,lambda changes=changes,fragment=fragment:
        refuse(lambda:reader.verify_bytes(BASE,dataclasses.replace(profile(BASE),**changes)),fragment))

for name,value in [('zero',0),('over-cap',reader.MAX_HEADER+8),('unaligned',len(HEADER)+1),('uint64-max',2**64-1)]:
    parameter_case('header_length_'+name,lambda value=value:
        refuse(lambda:read(struct.pack('<Q',value)+BASE[8:]),'Header length/padding bound'))

for name,raw in [('truncated-prefix',b'\x00'*8),('truncated-data',BASE[:-4]),('trailing-data',BASE+b'\x00'*4)]:
    parameter_case('coverage_'+name,lambda raw=raw:
        refuse(lambda:read(raw),'output size bound' if len(raw)<=8 else 'coverage/trailing/truncation'))

for name,raw,fragment in [
    ('malformed',b'{not-json}', 'Malformed UTF-8 JSON'),
    ('duplicate-top',b'{"x":1,"x":2}', 'Duplicate JSON key'),
    ('duplicate-inner',b'{"x":{"dtype":"F32","dtype":"F32"}}', 'Duplicate JSON key'),
    ('utf8-invalid',b'{"x":"\xff"}', 'Malformed UTF-8 JSON'),
    ('utf8-bom',b'\xef\xbb\xbf{}', 'ASCII opening brace'),
    ('utf16','{}'.encode('utf-16-le'), 'Malformed UTF-8 JSON'),
    ('leading-whitespace',b' {}', 'ASCII opening brace'),
    ('deep-nesting',b'{"x":'+b'['*2000+b'0'+b']'*2000+b'}', 'Malformed UTF-8 JSON'),
    ('json-nan',b'{"x":NaN}', 'Floating/nonfinite JSON'),
    ('json-infinity',b'{"x":Infinity}', 'Floating/nonfinite JSON'),
    ('json-float',b'{"x":1.0}', 'Floating/nonfinite JSON'),
    ('integer-overflow',b'{"x":'+b'9'*1000+b'}', 'JSON integer overflow')]:
    parameter_case('json_'+name,lambda raw=raw,fragment=fragment:
        refuse(lambda:read(with_header(raw)),fragment))

FIRST=ROWS[0]['key']
SECOND=ROWS[1]['key']
def descriptor_change(field,value):
    return lambda doc:doc[FIRST].__setitem__(field,value)
for name,change,fragment in [
    ('missing',lambda doc:doc.pop(FIRST),'54-key tensor schema'),
    ('unknown',lambda doc:doc.__setitem__('unknown',doc.pop(FIRST)),'54-key tensor schema'),
    ('metadata',lambda doc:doc.__setitem__('__metadata__',{}),'54-key tensor schema'),
    ('class-field',lambda doc:doc[FIRST].__setitem__('class','os.system'),'descriptor fields'),
    ('dtype',descriptor_change('dtype','F64'),'F32 dtype'),
    ('shape-wrong',descriptor_change('shape',[4]),'shape/type mismatch'),
    ('shape-bool',descriptor_change('shape',[True]),'shape/type mismatch'),
    ('shape-null',descriptor_change('shape',None),'shape/type mismatch'),
    ('shape-zero',descriptor_change('shape',[0]),'shape/type mismatch'),
    ('shape-negative',descriptor_change('shape',[-1]),'shape/type mismatch'),
    ('offset-bool',descriptor_change('data_offsets',[False,12]),'Integer data offset'),
    ('offset-negative',descriptor_change('data_offsets',[-4,8]),'Integer data offset'),
    ('offset-overflow',descriptor_change('data_offsets',[0,999999999]),'Integer data offset'),
    ('offset-alias',lambda doc:doc[SECOND].__setitem__('data_offsets',doc[FIRST]['data_offsets'][:]),'gap/overlap/alias'),
    ('offset-gap',descriptor_change('data_offsets',[4,16]),'gap/overlap/alias'),
    ('offset-overlap',lambda doc:doc[SECOND].__setitem__('data_offsets',[8,1544]),'gap/overlap/alias')]:
    parameter_case('schema_'+name,lambda change=change,fragment=fragment:
        refuse(lambda:read(changed_document(change)),fragment))

for name,raw in [
    ('pretty-json',json.dumps(DOCUMENT,sort_keys=True,indent=1).encode('utf-8')),
    ('reordered-keys',json.dumps(dict(reversed(list(DOCUMENT.items()))),separators=(',', ':')).encode('utf-8')),
    ('escaped-ascii-key',HEADER.rstrip(b' ').replace(b'classifier.bias',b'classifier\\u002ebias',1)),
    ('tab-padding',HEADER.rstrip(b' ')+b'\t'),
    ('extra-space-block',HEADER+b' '*8)]:
    parameter_case('canonical_'+name,lambda raw=raw:
        refuse(lambda:read(with_header(raw)),'Noncanonical header'))

for name,bits,offset in [('positive-infinity',0x7F800000,0),('negative-infinity',0xFF800000,4),
    ('quiet-nan',0x7FC00000,65536),('signaling-nan',0x7F800001,len(DATA)-4)]:
    def nonfinite(bits=bits,offset=offset):
        data=bytearray(DATA);struct.pack_into('<I',data,offset,bits)
        refuse(lambda:read(with_header(HEADER,bytes(data))),'Nonfinite binary32')
    parameter_case('data_'+name,nonfinite)

for name,value in [('zero',0),('negative',-1),('too-long',31),('nan',float('nan')),
    ('infinity',float('inf')),('bool',True),('huge-integer',10**1000)]:
    parameter_case('deadline_argument_'+name,lambda value=value:
        refuse(lambda:reader.verify_bytes(BASE,profile(BASE),deadline_seconds=value),'deadline bound'))

@case('deadline_refusal_during_hashing')
def hash_deadline():
    calls=[0]
    def clock():calls[0]+=1;return 0 if calls[0]<3 else 31
    with patched(reader.time,'monotonic',clock):
        refuse(lambda:read(),'deadline exceeded')

@case('deadline_refusal_after_json_parse')
def json_deadline():
    now=[0];original=reader.json.loads
    def loads(*args,**kwargs):
        value=original(*args,**kwargs);now[0]=31;return value
    with patched(reader.time,'monotonic',lambda:now[0]),patched(reader.json,'loads',loads):
        refuse(lambda:read(),'deadline exceeded')

@case('deadline_refusal_after_canonical_serialization')
def serialization_deadline():
    now=[0];original=reader.json.dumps
    def dumps(*args,**kwargs):
        value=original(*args,**kwargs);now[0]=31;return value
    with patched(reader.time,'monotonic',lambda:now[0]),patched(reader.json,'dumps',dumps):
        refuse(lambda:read(),'deadline exceeded')

@case('deadline_refusal_during_data_scan')
def scan_deadline():
    now=[0];original=reader.struct.iter_unpack
    def unpack(*args,**kwargs):
        yield from original(*args,**kwargs)
        now[0]=31
    with patched(reader.time,'monotonic',lambda:now[0]),patched(reader.struct,'iter_unpack',unpack):
        refuse(lambda:read(),'deadline exceeded')

@case('deadline_refusal_after_final_result_creation')
def final_deadline():
    now=[0];original=reader.VerifiedState
    def result(*args,**kwargs):
        value=original(*args,**kwargs);now[0]=31;return value
    with patched(reader.time,'monotonic',lambda:now[0]),patched(reader,'VerifiedState',result):
        refuse(lambda:read(),'deadline exceeded')

started=time.monotonic()
outcomes=[]
for name,fn in CASES:
    try:fn()
    except Exception as error:
        outcomes.append({'case':name,'passed':False,'error_type':type(error).__name__,'error':str(error)})
    else:outcomes.append({'case':name,'passed':True})
unchanged=all((HERE/name).read_bytes()==raw for name,raw in raw_inputs.items())
installed=all(getattr(os,name) is wrapper for name,wrapper in WRAPPERS.items()) and os.path.realpath is realpath_wrapper
heavy_after=sorted(name for name in sys.modules if name.split('.')[0] in HEAVY)
valid=not EVENTS and not PRELOADED and not heavy_after and unchanged and installed
passed=sum(row['passed'] for row in outcomes);failed=len(outcomes)-passed
exit_code=0 if failed==0 and valid else 1
print(json.dumps({'scope':'synthetic fixed plain-state reader proposal only',
    'cases':outcomes,'case_count':len(outcomes),'passed':passed,'failed':failed,
    'skipped':0,'qualification_exit':exit_code,'guard':{'valid':valid,'unexpected_events':EVENTS,
        'heavy_preloaded':PRELOADED,'heavy_after':heavy_after,'inputs_unchanged':unchanged,
        'lexical_wrappers_installed':installed},'input_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in raw_inputs.items()},
    'canonical_fixture_bytes':len(BASE),'canonical_fixture_sha256':hashlib.sha256(BASE).hexdigest(),
    'elapsed_seconds':round(time.monotonic()-started,6),
    'real_approval':False,'actual_artifact_access':False,'model_constructed':False},indent=2))
raise SystemExit(exit_code)
