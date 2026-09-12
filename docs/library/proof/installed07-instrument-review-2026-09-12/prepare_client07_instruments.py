"""Make reviewed path/auth-only copies; preserve shipped P4 tools and fixtures."""
from pathlib import Path
import ast,difflib,hashlib,json
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new,1)
def write(oldpath,name,new,scope):
    ast.parse(new);old=oldpath.read_text(encoding='utf8')
    with (s/name).open('x',encoding='utf8',newline='\n') as f:f.write(new)
    with (s/(name+'.diff')).open('x',encoding='utf8',newline='\n') as f:f.write(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=str(oldpath),tofile=name)))
    return {'source':str(oldpath),'adaptation':name,'scope':scope,'source_sha256':hashlib.sha256(oldpath.read_bytes()).hexdigest(),'adapted_sha256':hashlib.sha256((s/name).read_bytes()).hexdigest(),'executed':False}
auth=r"E:\AI\projects\uoink\installation-receipts\Agent Install 06\p4-client\profile\client\claude-config"
oldpath=r/'scripts/install_receipt/p4_operator.py';text=oldpath.read_text(encoding='utf8')
text=replace_once(text,'HERE = Path(__file__).resolve().parent','HERE = Path(__file__).resolve().parents[1] / "scripts" / "install_receipt"')
text=replace_once(text,'("launch-isolated.json" if args.client_route == "ordinary" else "launch-recall.json")','("launch.json" if args.client_route == "ordinary" else "launch-recall.json")')
anchor='        env["CLAUDE_CONFIG_DIR"] = str(client / "claude-config")'
insertion='''        env["CLAUDE_CONFIG_DIR"] = AUTH
        original_settings = client / ("settings.json" if args.client_route == "ordinary" else "settings-recall.json")
        expected = json.loads(original_settings.read_text(encoding="utf8"))
        expected["env"]["CLAUDE_CONFIG_DIR"] = env["CLAUDE_CONFIG_DIR"]
        overlay = profile.parent / ("settings-" + args.client_route + "-auth-overlay.json")
        if json.loads(overlay.read_text(encoding="utf8")) != expected:
            raise common.IsolationError("Auth overlay differs beyond the declared isolated credential namespace")
        launch["args"][launch["args"].index("--settings") + 1] = str(overlay)'''.replace('AUTH',repr(auth))
text=replace_once(text,anchor,insertion)
reviews=[write(oldpath,'p4_operator_client07.py',text,'Receipt adapter resolves the prepared launch.json and a frozen auth-directory-only settings overlay. Guards, scopes, original hashes and owned cleanup remain.')]
oldpath=s/'run_installed_client06.py';text=oldpath.read_text(encoding='utf8')
text=text.replace('Agent Install 06','Agent Install 07').replace('candidate-package-06-2026-09-11','candidate-package-07-2026-09-12').replace('p4-client/','p4/')
text=text.replace("root / 'p4/usage-confirmation.json'", "Path(r'E:\\AI\\projects\\uoink\\installation-receipts\\Agent Install 06\\p4-client\\usage-confirmation.json')")
text=replace_once(text,"'6697dffc30c98e97b22ecc9a5a35dfd3e8a91f5d'","'6a89189d601467eeff33d304c2c9b69cdd2e6d0b'")
text=replace_once(text,"client / 'launch-isolated.json'","client / 'launch.json'")
text=replace_once(text,"env = os.environ.copy(); env.update(launch['environment'])", "env = os.environ.copy(); env.update(launch['environment']); env['CLAUDE_CONFIG_DIR'] = "+repr(auth))
text=replace_once(text,"== client / 'claude-config'", "== Path("+repr(auth)+")")
text=replace_once(text,"r / 'scripts/install_receipt/p4_operator.py'", "r / '_scratch/p4_operator_client07.py'")
text=text.replace("root / 'p4-client'", "root / 'p4'")
reviews.append(write(oldpath,'run_installed_client07.py',text,'New app/package/profile labels, existing usage receipt and isolated auth namespace by reference. Uses the reviewed adapter; original seven prepared files remain immutable.'))
with (s/'client07-instrument-adaptations.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(reviews,indent=2)+'\n')
print(json.dumps(reviews,indent=2))
