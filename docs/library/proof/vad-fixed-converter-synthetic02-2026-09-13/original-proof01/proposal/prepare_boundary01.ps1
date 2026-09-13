$ErrorActionPreference='Stop'
$taskBase='E:\AI\projects\uoink\checkouts\Yoink-library'
$taskSource=Join-Path $taskBase '_scratch\vad-static-metadata-tail01\read_checkpoint_inventory.py'
$taskExpected='67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5'
if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {throw 'Reviewed ZIP source changed'}
$taskRaw=Get-Content -Raw -LiteralPath $taskSource
$taskFirst=$taskRaw.IndexOf('def read_exact(')
$taskLast=$taskRaw.IndexOf('def member_inventory(')
if($taskFirst -lt 0 -or $taskLast -le $taskFirst){throw 'Boundary extraction markers missing'}
$taskHeader=@'
"""Two exact reviewed ZIP-boundary functions; no artifact paths or pickle parser."""
import struct
import zipfile

MAX_CD = 2 * 1024 * 1024
MAX_MEMBERS = 256
MAX_NAME = 256

class Refusal(Exception):
    def __init__(self, reason, *, directory_entry=None):
        super().__init__(reason)
        self.directory_entry = directory_entry

def require(condition, reason, *, directory_entry=None):
    if not condition:
        raise Refusal(reason, directory_entry=directory_entry)


'@
$taskTarget=Join-Path $taskBase '_scratch\vad-fixed-converter-proposal01\zip_bounds.py'
if (Test-Path -LiteralPath $taskTarget) {throw 'Refuse overwrite'}
[IO.File]::WriteAllText($taskTarget,$taskHeader+$taskRaw.Substring($taskFirst,$taskLast-$taskFirst),[Text.UTF8Encoding]::new($false))
[ordered]@{source_sha256=$taskExpected;extracted_functions=@('read_exact','directory_bounds');generated_sha256=(Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant();exit=0} | ConvertTo-Json
