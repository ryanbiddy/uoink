import hashlib,io,json,os,subprocess,zipfile
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root / '_scratch/wheel-integrator13'
out=root / '_scratch/nltk-wheel-stored-build01'
out.mkdir(exist_ok=False)
original=root / '_scratch/nltk-wheel-worker-original13/_scratch'
first=next((original/'build_clean01').glob('*.whl')).read_bytes()
other=next((original/'build_py314').glob('*.whl')).read_bytes()
with zipfile.ZipFile(io.BytesIO(first)) as one,zipfile.ZipFile(io.BytesIO(other)) as two:
    assert one.namelist()==two.namelist()
    same_payloads=all(one.read(n)==two.read(n) for n in one.namelist())
    different_compressed=[n for n in one.namelist() if one.getinfo(n).compress_size != two.getinfo(n).compress_size]
    original_comparison={'same_payloads':same_payloads,'same_member_count':len(one.namelist()),
                        'different_compressed_sizes':len(different_compressed),'hashes':[hashlib.sha256(x).hexdigest() for x in (first,other)]}
(out / 'original-compression-comparison.json').write_text(json.dumps(original_comparison,indent=2)+'\n',encoding='utf8')
env=os.environ.copy()
for key in list(env):
    upper=key.upper()
    if any(s in upper for s in ('API_KEY','AUTH_TOKEN','ACCESS_TOKEN','BASE_URL','OAUTH_TOKEN')) or upper.startswith(('ANTHROPIC_','OPENAI_','GEMINI_API_','GOOGLE_API_','XAI_')):env.pop(key,None)
env['SOURCE_DATE_EPOCH']='1234567890'
bootstrap='''import runpy,sys
def guard(event,args):
    if event.startswith('socket.') or event=='subprocess.Popen': raise PermissionError('Offline wheel preparation')
sys.addaudithook(guard)
path=sys.argv.pop(1)
runpy.run_path(path,run_name='__main__')
'''
results=[]
for name,python in [('py314',Path(r'C:\Python314\python.exe')),('py313',root/'installer/staging/python/python.exe')]:
    destination=tree / '_scratch' / ('astra-stored-'+name+'-01')
    command=[str(python),'-I','-S','-B','-c',bootstrap,str(tree / 'scripts/build_nltk_pathsec_wheel.py'),
             '--wheel',str(tree / '_scratch/upstream/nltk-3.10.3-py3-none-any.whl'),'--out-dir',str(destination)]
    result=subprocess.run(command,cwd=tree,env=env,capture_output=True)
    (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
    row={'label':name,'command':command,'exit':result.returncode,'destination':str(destination)}
    results.append(row);(out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
    print(json.dumps(row),flush=True)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    wheel=next(destination.glob('*.whl'))
    row.update(sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),bytes=wheel.stat().st_size)
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
assert results[0]['sha256']==results[1]['sha256']
print(json.dumps({'cross_python_equal':True,'sha256':results[0]['sha256'],'bytes':results[0]['bytes'],'original':original_comparison}))
