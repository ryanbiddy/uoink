"""Independent synthetic decoder qualification, separate from original acceptance tests."""
import hashlib,json,subprocess,time
from pathlib import Path
import server

ROOT=Path(__file__).resolve().parents[1]
LGPL=ROOT/'_scratch/native-bin-lgpl-02/ffmpeg.exe'
GPL=ROOT/'_scratch/native-bin-gpl-01/ffmpeg.exe'

def _verified(path,expected):
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==expected

def test_shipping_decoder_handles_long_h264_and_audio(tmp_path):
    _verified(LGPL,'9c60da6c0b083110d59084ea39f60ae149aa3e031c3b4bb4f573fafa1c1e7cea')
    _verified(GPL,'b74bd2209fe38026ae9f73ad676e626599bdc1efd950fe32d40b23184fb1a060')
    rows=[]
    def run(command,timeout):
        start=time.monotonic()
        result=subprocess.run(list(map(str,command)),capture_output=True,timeout=timeout)
        rows.append({'command':list(map(str,command)),'exit':result.returncode,'seconds':time.monotonic()-start,'stdout':result.stdout.decode('utf8','replace'),'stderr':result.stderr.decode('utf8','replace')})
        (tmp_path/'native-observation.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
        assert result.returncode==0,result.stderr[-1500:]
        return result
    video=tmp_path/'synthetic-two-hours.mp4'
    run([GPL,'-y','-loglevel','error','-f','lavfi','-i','testsrc=size=192x108:rate=1:duration=7200','-pix_fmt','yuv420p','-c:v','libx264','-preset','ultrafast',video],60)
    shots=tmp_path/'shots';shots.mkdir()
    interval=server._screenshot_interval_for(7200,30)
    while server._estimated_screenshot_count([7200],interval)>server.MAX_SCREENSHOTS:
        interval+=1
    command=server._screenshot_ffmpeg_command(video,interval,shots/'shot_%04d.jpg')
    command[0]=str(LGPL)
    run(command,server._ffmpeg_timeout_for(7200))
    count=len(list(shots.glob('shot_*.jpg')))
    assert 0<count<=server.MAX_SCREENSHOTS
    source=tmp_path/'synthetic-tone.wav';target=tmp_path/'decoded-mono.wav'
    run([LGPL,'-y','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=2',source],20)
    run([LGPL,'-y','-loglevel','error','-i',source,'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',target],20)
    assert target.stat().st_size>=64000
    rows.append({'screenshots':count,'audio_bytes':target.stat().st_size,'synthetic_only':True,'shipping_variant':'LGPL','fixture_encoder':'GPL; not shipped'})
    (tmp_path/'native-observation.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
