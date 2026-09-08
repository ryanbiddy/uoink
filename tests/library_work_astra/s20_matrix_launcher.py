"""Fable-only S21 procedure. Pytest collection never starts this helper.

Execute explicitly after reviewing PHASE3-ACCEPTANCE-2026-09-08.md:
  python -B tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds 180

This is a disposable helper overlay, not an installed-build S22 certification.
Only media acquisition and transcription are synthetic. The HTTP handler,
registry, RSS parser, scheduler, ledger, podcast queue/worker, publication,
citations/clips and Phase 2 prepare_run use the candidate implementation.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(hold_seconds=0):
    """Fable-only S20 browser-matrix overlay (derived from the S21 launcher; not collected)."""
    import copy
    import hashlib
    import importlib.abc
    import importlib.util
    import json
    import os
    import shutil
    import socket
    import sqlite3
    import subprocess
    import sys
    import tempfile
    import threading
    import time
    import urllib.request
    from contextlib import ExitStack
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from unittest.mock import patch

    scratch = ROOT / '_scratch'
    scratch.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='s21-', dir=scratch)).resolve()
    assert root.is_relative_to(ROOT) and root != ROOT
    helper_root = root / 'helper'
    helper_root.mkdir()
    # Import byte-identical server code with disposable HERE/token/log paths.
    for name in ('server.py', 'VERSION'):
        shutil.copy2(ROOT / name, helper_root / name)
    shutil.copytree(ROOT / 'assets', helper_root / 'assets')
    sys.path.insert(0, str(ROOT))
    receipt = dict(procedure='S21', result='RUNNING', root=str(root),
                   fixture_downloads=0, fixture_transcripts=0, model_calls=0,
                   forbidden_attempts=[], connections=[], prepare_observations=[],
                   ownership_observations=[], candidate_sha=os.environ.get('S21_CANDIDATE_SHA'),
                   command=[sys.executable, '-B', *sys.argv], python=sys.version)
    ports, servers = set(), []
    original_connect, original_bind = socket.socket.connect, socket.socket.bind
    original_dns, original_db = socket.getaddrinfo, sqlite3.connect

    def denied(*args, **kwargs):
        receipt['forbidden_attempts'].append('process or forbidden network call')
        raise AssertionError('S21 forbids child processes and non-fixture networking')

    def model_denied(*args, **kwargs):
        receipt['model_calls'] += 1
        raise AssertionError('S21 forbids model execution')

    def connect(sock, address):
        if not (address[0] == '127.0.0.1' and address[1] in ports and address[1] != 5179):
            denied()
        receipt['connections'].append(list(address))
        return original_connect(sock, address)

    def bind(sock, address):
        if address != ('127.0.0.1', 0):
            denied()
        return original_bind(sock, address)

    def dns(host, port, *args, **kwargs):
        if not (host == '127.0.0.1' and int(port) in ports and int(port) != 5179):
            denied()
        return original_dns(host, port, *args, **kwargs)

    def database(path, *args, **kwargs):
        assert not str(path).startswith('file:')
        assert Path(path).resolve().is_relative_to(root), path
        return original_db(path, *args, **kwargs)

    class NoModels(importlib.abc.MetaPathFinder):
        availability_probe = False

        def find_spec(self, fullname, path=None, target=None):
            if fullname == 'whisperx' and self.availability_probe:
                # Fail the cold-boot probe without loading a model runtime.
                raise ModuleNotFoundError('WhisperX disabled for the S21 availability probe', name=fullname)
            if fullname.split('.')[0] in {'torch', 'whisperx', 'faster_whisper', 'transformers', 'anthropic', 'openai'}:
                model_denied()
            return None

    def serve(httpd):
        assert httpd.server_address[0] == '127.0.0.1' and httpd.server_address[1] != 5179
        ports.add(httpd.server_address[1])
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        servers.append((httpd, worker))
        return 'http://127.0.0.1:' + str(httpd.server_address[1])

    model_guard = NoModels()
    sys.meta_path.insert(0, model_guard)
    idx = None
    with ExitStack() as stack:
        for key in ('LOCALAPPDATA', 'APPDATA', 'XDG_DATA_HOME', 'UOINK_DATA_ROOT', 'UOINK_OUTPUT_ROOT', 'TEMP', 'TMP'):
            stack.enter_context(patch.dict(os.environ, {key: str(root)}))
        for obj, name, replacement in (
            (socket.socket, 'connect', connect), (socket.socket, 'connect_ex', denied),
            (socket.socket, 'bind', bind), (socket.socket, 'sendto', denied),
            (socket, 'getaddrinfo', dns), (subprocess, 'Popen', denied),
            (os, 'system', denied), (sqlite3, 'connect', database),
            (sqlite3.dbapi2, 'connect', database),
        ):
            stack.enter_context(patch.object(obj, name, replacement))
        if hasattr(os, 'startfile'):
            stack.enter_context(patch.object(os, 'startfile', denied))
        try:
            import _platform
            stack.enter_context(patch.object(_platform, 'user_data_dir', lambda: root))
            stack.enter_context(patch.object(_platform, 'desktop_dir', lambda: root / 'output'))
            # Only this import-time availability check is exempt from model-call
            # accounting. All guards stay installed, including the runtime block.
            model_guard.availability_probe = True
            try:
                import whisper_runner
            finally:
                model_guard.availability_probe = False
            spec = importlib.util.spec_from_file_location('server', helper_root / 'server.py')
            server = importlib.util.module_from_spec(spec)
            sys.modules['server'] = server
            spec.loader.exec_module(server)
            import index
            import podcasts
            import source_subscriptions as ss
            from library_work import RequestContext

            # The production address checks remain active for every other host.
            # No registry option can enable this allowance.
            reject_ip, check_host = ss._reject_private_ip, ss._check_resolved_host
            stack.enter_context(patch.object(ss, '_reject_private_ip',
                lambda host: None if host == '127.0.0.1' else reject_ip(host)))
            stack.enter_context(patch.object(ss, '_check_resolved_host',
                lambda host: None if host == '127.0.0.1' else check_host(host)))
            # Ignore machine proxy settings for the two fixture endpoints only.
            stack.enter_context(patch.dict(os.environ, {'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'}))
            clock = [int(time.time() * 1000)]
            idx = index.Index.open(root / 'index.db')
            server._index_singleton = idx
            server.maybe_toast = lambda *a, **k: None
            server._anthropic_messages = model_denied
            server._keyring = None
            settings = server._read_settings()
            for key, value in list(settings.items()):
                if isinstance(value, bool) and ('enabled' in key or key.startswith('auto_')):
                    settings[key] = False
            settings.update(library_apply_enabled=False, diarization_default=False)
            server._write_settings(settings)

            # Deterministic fixture input; one cue makes exact clip timing testable.
            transcript = dict(model='synthetic-S21', language='en', diarization_ran=False,
                              segments=[dict(start=12.5, end=21.75,
                                  text='S21 fixture: durable capture waits for complete publication.')])
            def observe_ownership(boundary):
                with idx._lock:
                    start = dict(idx._conn.execute(
                        "SELECT * FROM source_capture_starts WHERE state='started'").fetchone())
                assert start['owner_instance'] == service.instance_id == server._source_instance_id()
                assert service.backend.owns(start['capture_key']), boundary
                assert service.backend.holds_execution(start), boundary
                competitor = ss.CaptureLock.try_acquire(root, start['capture_key'])
                if competitor is not None:
                    competitor.release()
                    raise AssertionError(f'{boundary}: capture lock was available to another holder')
                claim = service.backend.execution_claim(start)
                receipt['ownership_observations'].append(dict(
                    boundary=boundary, start_id=start['start_id'], capture_key=start['capture_key'],
                    instance=start['owner_instance'], claim=claim, capture_lock_exclusive=True))

            def before_acquisition(boundary):
                # S20 matrix: many captures run in one overlay, so the S21 single-item
                # invariants do not apply; only the ownership observation is kept.
                try:
                    observe_ownership(boundary)
                except Exception as exc:
                    receipt.setdefault('ownership_exceptions', []).append(f'{boundary}: {type(exc).__name__}: {exc}')

            def download(db, episode_id, *, data_root, **kwargs):
                before_acquisition('download')
                receipt['fixture_downloads'] += 1
                episode = podcasts.get_episode(db, episode_id)
                with urllib.request.urlopen(episode['audio_url'], timeout=300) as response:  # S20: slow_audio mode holds this open
                    body = response.read(1025)
                assert body == b'S21 SYNTHETIC AUDIO PLACEHOLDER'
                audio = root / 'fixture.mp3'
                audio.write_bytes(body)
                with db.write_transaction() as conn:
                    conn.execute('UPDATE podcast_episodes SET audio_local_path=? WHERE id=?', (str(audio), episode_id))
                return dict(ok=True, audio_local_path=str(audio))

            def synthetic_transcript(*args, **kwargs):
                before_acquisition('transcription')
                receipt['fixture_transcripts'] += 1
                return copy.deepcopy(transcript)

            original_publisher = podcasts.episode_to_corpus

            def publish(db, episode_id, **kwargs):
                before_acquisition('publication')
                result = original_publisher(db, episode_id, **kwargs)
                observe_ownership('publication_returned')
                return result

            stack.enter_context(patch.object(podcasts, 'download_episode_audio', download))
            stack.enter_context(patch.object(podcasts, 'episode_to_corpus', publish))
            stack.enter_context(patch.object(whisper_runner, 'is_whisperx_available', lambda: True))
            stack.enter_context(patch.object(whisper_runner, 'is_model_downloaded', lambda *a, **k: True))
            stack.enter_context(patch.object(whisper_runner, 'transcribe_audio', synthetic_transcript))
            stack.enter_context(patch.object(whisper_runner, 'set_current_thread_below_normal', lambda: False))
            service = ss.SourceSubscriptionService(idx, clock=lambda: clock[0],
                backend=server._ServerCaptureBackend(), instance_id=server._source_instance_id(), jitter=lambda: 0)
            server._source_service_instance = service
            incarnation = ss.process_incarnation(root)
            incarnation_path = root / ss.INSTANCE_DIR / f'{incarnation.token}.json'
            incarnation_record = json.loads(incarnation_path.read_text(encoding='utf-8'))
            assert incarnation_record['pid'] == os.getpid()
            assert Path(incarnation_record['root']).resolve() == root
            assert incarnation_record['token'] == incarnation.token
            receipt['incarnation'] = dict(identity=incarnation.identity, record=incarnation_record,
                path=str(incarnation_path.relative_to(root)))
            taxonomy_path = ROOT / 'docs/library/taxonomy-v3-2026-09-07.json'
            prompt_path = ROOT / 'scripts/librarian/prompts/assign.md'
            taxonomy = json.loads(taxonomy_path.read_text(encoding='utf-8'))
            assert taxonomy['status'] == 'approved' and taxonomy['version_id'] == 'taxonomy-v3-2026-09-07'
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            assert sha(prompt_path) == 'cd22a3c1819f693bc921033847e21b18dfac6bbac138da6162af3a0244d12f32'
            assert sha(taxonomy_path) == 'c3fdb4fb0c3f89c68b06676f7613c75d3a293787d28c32b0a5adb9fa91e4fdf7'
            receipt['input_hashes'] = {str(p.relative_to(ROOT)): sha(p) for p in (
                ROOT / 'server.py', ROOT / 'source_subscriptions.py', ROOT / 'podcasts.py',
                ROOT / 'clips.py', ROOT / 'index.py', ROOT / 'whisper_runner.py',
                ROOT / 'library_work.py', ROOT / 'library_cards.py',
                ROOT / 'migrations/0028_source_subscriptions.sql',
                Path(__file__).resolve(), taxonomy_path, prompt_path)}
            library = idx.library_service()
            approved = library.approve_taxonomy(RequestContext(authenticated=True, operator=True),
                dict(version_id=taxonomy['version_id'], nodes=taxonomy['nodes']))
            assert approved['ok'], approved
            configured = service.configure_classification_policy(
                ss.RequestContext(authenticated=True, operator=True),
                dict(version_id=taxonomy['version_id'], prompt_hash=sha(prompt_path)))
            assert configured['ok'], configured
            original_prepare = library.prepare_run

            def prepare(context, args):
                video_id = args['video_ids'][0]
                with sqlite3.connect(root / 'index.db') as conn:
                    pass  # S20 matrix: many succeeded starts
                    for table in ('yoinks', 'citations', 'clips'):
                        assert conn.execute(f'SELECT COUNT(*) FROM {table} WHERE video_id=?', (video_id,)).fetchone()[0] == 1
                row = idx.get_yoink(video_id)
                assert Path(row['corpus_path']).is_file() and Path(row['sidecar_path']).is_file()
                receipt['prepare_observations'].append(dict(after_commit=True, video_id=video_id))
                return original_prepare(context, args)
            library.prepare_run = prepare
            feed_state = {'entry': False}
            feed_base = ''

            feed_state.update(mode='ok', entries=0, slow_s=0)

            class FeedHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if feed_state['mode'] == 'error' and self.path == '/feed.xml':
                        self.send_error(500, 'S20 injected feed error')
                        return
                    if feed_state['mode'] == 'slow' and self.path in ('/feed.xml', '/fixture.mp3'):
                        time.sleep(feed_state['slow_s'])
                    if feed_state['mode'] == 'slow_audio' and self.path == '/fixture.mp3':
                        time.sleep(feed_state['slow_s'])
                    if self.path == '/fixture.mp3':
                        body = b'S21 SYNTHETIC AUDIO PLACEHOLDER'
                    elif self.path == '/feed.xml':
                        items = ''.join(
                            f'<item><guid>s20-entry-{i}</guid><title>S20 matrix item {i}</title>'
                            f'<link>{feed_base}/episode/{i}</link><enclosure url="{feed_base}/fixture.mp3" type="audio/mpeg"/>'
                            f'<pubDate>Mon, 07 Sep 2026 {i:02d}:00:00 GMT</pubDate></item>'
                            for i in range(1, feed_state['entries'] + 1))
                        body = f'<rss version="2.0"><channel><title>S20 matrix fixture</title>{items}</channel></rss>'.encode()
                    elif self.path.startswith('/episode'):
                        body = b'S20 fixture episode'
                    else:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            feed_base = serve(ThreadingHTTPServer(('127.0.0.1', 0), FeedHandler))
            helper = server._YoinkHTTPServer(('127.0.0.1', 0), server.Handler)
            server.PORT = helper.server_address[1]
            helper_base = serve(helper)
            receipt.update(helper_url=helper_base, feed_url=feed_base + '/feed.xml')

            def request(path, body=None):
                headers = {'X-Uoink-Token': server.TOKEN, 'Origin': helper_base,
                           'Sec-Fetch-Site': 'same-origin', 'Content-Type': 'application/json'}
                req = urllib.request.Request(helper_base + path, headers=headers,
                    data=json.dumps(body).encode() if body is not None else None)
                with urllib.request.urlopen(req, timeout=5) as response:
                    result = json.load(response)
                assert result['ok'], result
                return result

            helper_ref = {'helper': helper, 'worker': None}
            for httpd, worker in servers:
                if httpd is helper:
                    helper_ref['worker'] = worker

            class ControlHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    from urllib.parse import urlparse, parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    out = {}
                    if 'mode' in q:
                        feed_state['mode'] = q['mode'][0]
                        feed_state['slow_s'] = int(q.get('slow_s', ['20'])[0])
                    if 'entries' in q:
                        feed_state['entries'] = int(q['entries'][0])
                    if 'advance_min' in q:
                        clock[0] += int(q['advance_min'][0]) * 60_000
                        out['clock_ms'] = clock[0]
                    if 'tick' in q:
                        server._podcast_feed_scheduler_tick()
                        out['ticked'] = True
                    if 'restart' in q:
                        # Helper restart: close the listening helper, re-bind on a fresh
                        # ephemeral port (the guard forbids fixed ports), then run the
                        # production startup reconciliation exactly as server startup does.
                        old = helper_ref['helper']
                        old.shutdown(); old.server_close(); helper_ref['worker'].join(timeout=5)
                        new = server._YoinkHTTPServer(('127.0.0.1', 0), server.Handler)
                        server.PORT = new.server_address[1]
                        worker = threading.Thread(target=new.serve_forever, daemon=True); worker.start()
                        ports.add(new.server_address[1]); servers.append((new, worker))
                        helper_ref['helper'], helper_ref['worker'] = new, worker
                        out['reconcile'] = server._source_service().reconcile_on_startup()
                        out['restarted'] = True
                        out['dashboard'] = 'http://127.0.0.1:%d/dashboard' % server.PORT
                        receipt.setdefault('restarts', []).append(out['dashboard'])
                        print('S20 dashboard (restarted): ' + out['dashboard'], flush=True)
                    if 'state' in q:
                        with idx._lock:
                            out['sources'] = [dict(r) for r in idx._conn.execute(
                                'SELECT * FROM source_subscriptions')]
                            out['starts'] = [dict(r) for r in idx._conn.execute(
                                'SELECT * FROM source_capture_starts')]
                            out['items'] = [dict(r) for r in idx._conn.execute(
                                'SELECT * FROM source_items')]
                            out['receipts'] = idx._conn.execute('SELECT COUNT(*) FROM source_consent_receipts').fetchone()[0]
                    out.update(feed=dict(feed_state), clock_ms=clock[0])
                    body = json.dumps(out, default=str).encode()
                    self.send_response(200); self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

                def log_message(self, *args):
                    pass

            control_base = serve(ThreadingHTTPServer(('127.0.0.1', 0), ControlHandler))
            receipt.update(result='S20 MATRIX HOLD', control_url=control_base)
            print('S20 dashboard: ' + helper_base + '/dashboard', flush=True)
            print('S20 control: ' + control_base + '/ctl', flush=True)
            print('S20 feed: ' + feed_base + '/feed.xml', flush=True)
            if hold_seconds:
                threading.Event().wait(hold_seconds)
            assert receipt['model_calls'] == 0 and receipt['forbidden_attempts'] == []
        except BaseException as exc:
            receipt.update(result='FAIL', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            for httpd, worker in reversed(servers):
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)
            if idx is not None:
                with sqlite3.connect(root / 'evidence.db') as evidence:
                    with idx._lock:
                        idx._conn.backup(evidence)
                receipt['evidence_sha256'] = hashlib.sha256((root / 'evidence.db').read_bytes()).hexdigest()
                idx.close()
            receipt['artifact_hashes'] = {
                str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob('*') if path.is_file()
                and (path.name == 'evidence.db' or path.suffix in {'.md', '.json', '.txt', '.log'})
                and path.name not in {'token.txt', 'settings.json', 'jobs.json', 'receipt.json'}
                and helper_root / 'assets' not in path.parents}
            sys.meta_path.remove(model_guard)
            (root / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print('S20 receipt: ' + str(root / 'receipt.json'), flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-s20-matrix', action='store_true', required=True)
    parser.add_argument('--hold-seconds', type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 1800:
        parser.error('--hold-seconds must be 0..600')
    run(args.hold_seconds)
