"""Public dependency metadata only; no credentials, binaries or media fetched."""
import datetime as dt,json,urllib.request
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/native-release-metadata-01';out.mkdir(exist_ok=False)
urls={'btbn-releases.json':'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases?per_page=3',
      'ffmpeg-security.html':'https://ffmpeg.org/security.html',
      'python-versions.json':'https://endoflife.date/api/python.json'}
# Only first-party records determine decisions. Do not use a third-party lifecycle
# service when the official CPython branch-status documentation is available.
urls['python-support.html']='https://devguide.python.org/versions/'
urls.pop('python-versions.json')
records=[]
for name,url in urls.items():
 req=urllib.request.Request(url,headers={'User-Agent':'Uoink-release-review','Accept':'application/vnd.github+json' if name.endswith('.json') else 'text/html'})
 with urllib.request.urlopen(req,timeout=30) as response:data=response.read();status=response.status
 (out/name).write_bytes(data);records.append({'url':url,'status':status,'file':name,'bytes':len(data),'utc':dt.datetime.now(dt.timezone.utc).isoformat()})
(out/'fetch.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
releases=json.loads((out/'btbn-releases.json').read_text())
for release in releases:
 print(json.dumps({'tag':release['tag_name'],'published_at':release['published_at'],'html_url':release['html_url'],'assets':[{'name':x['name'],'url':x['browser_download_url'],'digest':x.get('digest'),'bytes':x['size']} for x in release['assets'] if 'win64' in x['name'] or 'sha256' in x['name'].lower()]},indent=2))
