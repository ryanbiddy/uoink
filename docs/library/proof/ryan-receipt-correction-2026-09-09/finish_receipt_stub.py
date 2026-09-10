from pathlib import Path
import re
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\269acc98-ac8\gemini')
p=w/'scripts/install_receipt/stub_helper.py';s=p.read_text(encoding='utf8')
s=s.replace('import argparse\n','import argparse\nimport hashlib\n').replace('import urllib.parse\n','import urllib.parse\nimport urllib.request\nimport xml.etree.ElementTree as ET\n')
s=s.replace('str(abs(hash(url)) % 10**12)','hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]')
s=s.replace('str(abs(hash(body["url"])) % 10**12)','hashlib.sha256(body["url"].encode("utf-8")).hexdigest()[:24]')
a=s.index('        def _extract(');b=s.index('        def _standing_capture(',a)
s=s[:a]+'''        def _extract(self, body: dict):
            # Extraction acknowledges the declared source; only the explicit
            # publication route creates corpus/ledger rows in this instrument.
            return self._json(200, {"ok": True, "synthetic": True,
                                    "url": body.get("url"), "publication": "none"})

'''+s[b:]
a=s.index('        def _podcast_feed_poll(');b=s.index('        def _refresh(',a)
s=s[:a]+'''        def _podcast_feed_poll(self, body: dict):
            feed_id = body.get("feed_id")
            row = state.conn.execute("SELECT * FROM podcast_feeds WHERE id=?",
                                     (feed_id,)).fetchone()
            if row is None:
                return self._json(404, {"ok": False, "error": "missing feed"})
            source = urllib.parse.urlsplit(row["feed_url"])
            fixture = urllib.parse.urlsplit(os.environ.get("C22_FIXTURE_LOOPBACK", ""))
            if (source.scheme != "http" or source.hostname != "c22-fixture.invalid"
                    or fixture.scheme != "http" or fixture.hostname != "127.0.0.1"
                    or not fixture.port or fixture.port == FORBIDDEN_PORT):
                return self._json(400, {"ok": False, "error": "undeclared fixture"})
            target = urllib.parse.urlunsplit(("http", fixture.netloc, source.path,
                                             source.query, ""))
            try:
                with urllib.request.urlopen(target, timeout=5) as response:
                    xml = response.read(1024 * 1024 + 1)
                if len(xml) > 1024 * 1024:
                    raise ValueError("fixture feed too large")
                entries = ET.fromstring(xml).findall("./channel/item")
            except Exception as exc:
                return self._json(502, {"ok": False, "error": type(exc).__name__})
            with state.lock:
                for entry in entries:
                    guid, title = entry.findtext("guid"), entry.findtext("title")
                    if not guid:
                        continue
                    state.conn.execute(
                        "INSERT OR IGNORE INTO podcast_episodes"
                        "(feed_id,guid,title,status,source_id) VALUES (?,?,?,'discovered',?)",
                        (feed_id, guid, title, row["source_id"]))
                state.conn.commit()
            return self._json(200, {"ok": True, "polled": True, "feed_id": feed_id})

        def _podcast_episode_download(self, body: dict):
            ep_id = body.get("episode_id")
            with state.lock:
                row = state.conn.execute("SELECT * FROM podcast_episodes WHERE id=?",
                                         (ep_id,)).fetchone()
                if row is None:
                    return self._json(404, {"ok": False, "error": "missing episode"})
                audio = Path(os.environ.get("C22_SYNTHETIC_AUDIO_PATH", ""))
                if not audio.is_file():
                    return self._json(409, {"ok": False, "error": "missing synthetic audio"})
                state.conn.execute("UPDATE podcast_episodes SET status='downloaded' WHERE id=?",
                                   (ep_id,))
                state.conn.commit()
            return self._json(200, {"ok": True, "synthetic": True, "downloaded": True})

        def _podcast_episode_transcribe(self, body: dict):
            ep_id = body.get("episode_id")
            with state.lock:
                row = state.conn.execute("SELECT * FROM podcast_episodes WHERE id=?",
                                         (ep_id,)).fetchone()
                if row is None:
                    return self._json(404, {"ok": False, "error": "missing episode"})
                transcript = Path(os.environ.get("C22_SYNTHETIC_TRANSCRIPT_PATH", ""))
                if row["status"] not in ("downloaded", "transcribed") or not transcript.is_file():
                    return self._json(409, {"ok": False, "error": "missing synthetic input"})
                state.conn.execute(
                    "UPDATE podcast_episodes SET status='transcribed',transcript_local_path=? WHERE id=?",
                    (str(transcript), ep_id))
                state.conn.commit()
            return self._json(200, {"ok": True, "synthetic": True, "model_invoked": False})

        def _podcast_episode_to_corpus(self, body: dict):
            ep_id = body.get("episode_id")
            with state.lock:
                ep = state.conn.execute(
                    "SELECT e.*,f.feed_url FROM podcast_episodes e "
                    "JOIN podcast_feeds f ON f.id=e.feed_id WHERE e.id=?", (ep_id,)).fetchone()
                if ep is None:
                    return self._json(404, {"ok": False, "error": "missing episode"})
                if ep["status"] != "transcribed" or not Path(ep["transcript_local_path"] or "").is_file():
                    return self._json(409, {"ok": False, "error": "transcript required"})
                capture_key = "podcast:" + hashlib.sha256(ep["feed_url"].encode("utf-8")).hexdigest()[:24]
                existing = state.conn.execute(
                    "SELECT * FROM source_capture_starts WHERE capture_key=?", (capture_key,)).fetchone()
                if existing:
                    return self._json(200, {"ok": True, "synthetic": True, "deduped": True})
                start_id, item_id, video_id = (prefix + capture_key[-16:] for prefix in ("st_", "si_", "vid_"))
                corpus = state.profile / "output" / video_id / "item.md"
                corpus.parent.mkdir(parents=True, exist_ok=True)
                transcript = json.loads(Path(ep["transcript_local_path"]).read_text(encoding="utf-8"))
                corpus.write_text("C22 synthetic publication\\n" + json.dumps(transcript) + "\\n", encoding="utf-8")
                state.conn.execute(
                    "INSERT INTO source_capture_starts(start_id,source_id,capture_key,state,charged,origin,item_id,started_at_ms) "
                    "VALUES (?,?,?,'succeeded',0,'manual',?,?)",
                    (start_id, ep["source_id"], capture_key, item_id, int(time.time()*1000)))
                state.conn.execute(
                    "INSERT INTO source_items(item_id,source_id,entry_id,capture_key,outcome) VALUES (?,?,?,?,'committed')",
                    (item_id, ep["source_id"], ep["guid"], capture_key))
                state.conn.execute(
                    "INSERT INTO yoinks(video_id,title,corpus_path,sidecar_path) VALUES (?,?,?,?)",
                    (video_id, ep["title"], str(corpus), str(corpus.with_suffix(".json"))))
                state.conn.commit()
            return self._json(200, {"ok": True, "synthetic": True, "video_id": video_id})

'''+s[b:]
p.write_text(s,encoding='utf8')
print('Completed synthetic API repair; no tests or oracles modified by this script')
