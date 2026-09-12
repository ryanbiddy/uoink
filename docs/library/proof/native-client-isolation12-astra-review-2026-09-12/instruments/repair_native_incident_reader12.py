from pathlib import Path
import ast,difflib,json
r=Path(__file__).resolve().parents[1];s=r/'_scratch'
old=(s/'review_native_incident12.py').read_text(encoding='utf8')
new=old.replace("out=s/'native-client-incident12-review'","out=s/'native-client-incident12-review02'")
needle='if(process.env.CLAUDE_USER_DATA_DIR){let e=process.env.CLAUDE_USER_DATA_DIR;E.app.setPath("userData",e)'
assert old.count(needle)==1
new=new.replace(needle,'let e=process.env.CLAUDE_USER_DATA_DIR;E.app.setPath("userData",e)')
ast.parse(new)
(s/'review_native_incident12_02.py').write_text(new,encoding='utf8',newline='\n')
(s/'review_native_incident12_02.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='literal-if-assumption',tofile='actual-setter-literal')),encoding='utf8')
(s/'native-client-incident12-review/reader-failure.json').write_text(json.dumps({'result':'reader failed before evidence record was written','error':'ValueError: substring not found','reason':'The setter follows a compound if condition; the reader incorrectly required a standalone if prefix. Match the actual setter body and retain deletion-before-setter and all byte/hash checks.','next':'fresh review02, no application or product scenario rerun'},indent=2)+'\n',encoding='utf8')
