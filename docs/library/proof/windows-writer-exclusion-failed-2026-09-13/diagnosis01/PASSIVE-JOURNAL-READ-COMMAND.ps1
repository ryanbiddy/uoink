$taskPath='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\windows-reservation-writer-exclusion02\registry\4640b95540b94d05-516b2100000002000000000000000000.journal'
$taskInfo=Get-Item -LiteralPath $taskPath
if($taskInfo.Length -le 6 -or $taskInfo.Length -gt 16534){throw 'Generated journal diagnostic bound'}
$taskRaw=[IO.File]::ReadAllBytes($taskPath)
if([Text.Encoding]::ASCII.GetString($taskRaw,0,6) -cne "UORS1`n"){throw 'Generated journal header differs'}
$taskOffset=6;$taskRows=@();$taskPrevious='0'*64
while($taskOffset -lt $taskRaw.Length){
 if($taskRows.Count -ge 4 -or $taskRaw.Length-$taskOffset -lt 4){throw 'Generated frame count/header bound'}
 $taskLength=([uint32]$taskRaw[$taskOffset]*16777216)+([uint32]$taskRaw[$taskOffset+1]*65536)+([uint32]$taskRaw[$taskOffset+2]*256)+[uint32]$taskRaw[$taskOffset+3]
 $taskOffset+=4
 if($taskLength -le 0 -or $taskLength -gt 4096 -or $taskRaw.Length-$taskOffset -lt $taskLength+32){throw 'Generated frame length bound'}
 $taskPayload=[byte[]]$taskRaw[$taskOffset..($taskOffset+$taskLength-1)]
 $taskDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskPayload)).ToLowerInvariant()
 $taskRecorded=[Convert]::ToHexString([byte[]]$taskRaw[($taskOffset+$taskLength)..($taskOffset+$taskLength+31)]).ToLowerInvariant()
 if($taskDigest -cne $taskRecorded){throw 'Generated journal checksum mismatch'}
 $taskData=[Text.Encoding]::UTF8.GetString($taskPayload)|ConvertFrom-Json
 if($taskData.previous -cne $taskPrevious){throw 'Generated journal chain differs'}
 $taskRows += [ordered]@{sequence=$taskData.sequence;phase=$taskData.phase;physical=$taskData.physical;process=$taskData.process;reason=$taskData.reason;payload_bytes=$taskLength;digest=$taskDigest}
 $taskPrevious=$taskDigest;$taskOffset+=$taskLength+32
}
[ordered]@{path=$taskPath;bytes=$taskRaw.Length;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskRaw)).ToLowerInvariant();frames=$taskRows;scope='Bounded saved generated journal inspection only; no candidate decoder or native calls'}|ConvertTo-Json -Depth 8
