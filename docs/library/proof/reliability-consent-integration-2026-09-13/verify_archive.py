"""Verify documentary ZIP/member hashes and original preparation seals; no execution."""
import argparse,hashlib,json,ntpath,zipfile
from pathlib import Path,PurePosixPath
OUT=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def verify(check_source_disk=False):
    manifest=json.loads((OUT/'ZIP-MEMBERS-SHA256.json').read_bytes())
    receipt=json.loads((OUT/'ARCHIVE-RECEIPT.json').read_bytes())
    listing=json.loads((OUT/'INPUT-LIST.json').read_bytes())
    expected={row['member']:row for row in manifest['members']}
    assert len(expected)==manifest['member_count']==listing['file_count']==563
    archive_path=OUT/'receipts.zip'
    assert archive_path.stat().st_size==receipt['zip_bytes']<32*1024*1024
    with archive_path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==receipt['zip_sha256']
    with zipfile.ZipFile(archive_path) as archive:
        infos=archive.infolist()
        assert len(infos)==len(expected) and {info.filename for info in infos}==set(expected)
        assert sum(info.file_size for info in infos)==manifest['total_uncompressed_bytes']==7194435
        for info in infos:
            path=PurePosixPath(info.filename)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename
            row=expected[info.filename]
            assert info.file_size==row['bytes']<2*1024*1024
            raw=archive.read(info)
            assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],info.filename
        seals=[('instrument01',31,'a06eee5c9ecc0b550b91dba9a930d91adfcb8588cc8ab68cf0be24f6e8dc2362'),
            ('node02',36,'0f82a7df43e7587ebc42f7c1556c0cbdd950bf1d37a3aeec27c22895a53d0c8d'),
            ('node03',33,'1dfd0be4152016645d75b680e52d8ebb5b53034f0ec02806c5e097fb3070095f'),
            ('node04',35,'a20480f1f7b3f24311a2422848a99c02d83bb7c73c5a9d1b2a6f936c5320a09a')]
        for label,count,digest in seals:
            prefix='preparation/'+label+'/'
            raw=archive.read(prefix+'SHA256.json');assert sha(raw)==digest
            old=json.loads(raw);assert old['payload_count']==count
            for row in old['payloads']:
                raw=archive.read(prefix+row['file'])
                assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
    if check_source_disk:
        roots=[r'E:\AI\projects\uoink\checkouts\Yoink-library',
            r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\0851b440-86a\grok']
        roots=[ntpath.normcase(ntpath.abspath(root)) for root in roots]
        for row in listing['entries']:
            assert {key:row[key] for key in ['member','bytes','sha256']}==expected[row['member']]
            name=ntpath.normcase(ntpath.abspath(row['source']))
            assert any(name.startswith(root+'\\') for root in roots)
            assert r'\uoink\index.db' not in name and not name.endswith(('.exe','.dll','.bin','.pt','.db','.whl'))
            raw=Path(row['source']).read_bytes()
            assert len(raw)==row['bytes'] and sha(raw)==row['sha256'],row['member']
    return {'valid':True,'verified_members':len(expected),'verified_uncompressed_bytes':manifest['total_uncompressed_bytes'],
        'original_preparation_seals_verified':[31,36,33,35],'source_disk_checked':check_source_disk,
        'tests_or_product_executed':False}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check-source-disk',action='store_true')
    args=parser.parse_args();print(json.dumps(verify(args.check_source_disk)))
