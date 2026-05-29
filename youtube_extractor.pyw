"""Uoink — GUI wrapper around yt-dlp + ffmpeg."""

import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

try:
    from win11toast import toast as _toast
    HAVE_TOAST = True
except Exception:
    HAVE_TOAST = False

# Hide subprocess console windows on Windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SUBPROCESS_KW = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}


# ---------- helpers reused verbatim from yt_extract.py ----------

def slugify(text: str) -> str:
    return re.sub(r"[^\w\-]+", "_", text.strip())[:80].strip("_")


def fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_srt(srt_path: Path):
    """Yield (start_sec, end_sec, text) from an SRT file."""
    content = srt_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s+-->\s+(\d+):(\d+):(\d+)[,.](\d+)"
    )
    blocks = re.split(r"\n\s*\n", content.strip())
    seen = set()
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        m = pattern.search(lines[1] if pattern.search(lines[1] or "") else " ".join(lines[:2]))
        if not m:
            for ln in lines:
                m = pattern.search(ln)
                if m:
                    break
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        text_lines = [ln for ln in lines if not pattern.search(ln) and not ln.isdigit()]
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text and text not in seen:
            seen.add(text)
            yield start, end, text


# ---------- extraction worker ----------

def extract(url: str, interval: int, status_q: queue.Queue, result_q: queue.Queue):
    """Run the full extraction. Push string updates to status_q.
    On completion, push ('ok', folder_path) or ('err', message) to result_q."""
    try:
        out_root = Path(os.environ["USERPROFILE"]) / "Desktop" / "Uoink"
        out_root.mkdir(parents=True, exist_ok=True)

        status_q.put("Fetching video title...")
        title = subprocess.check_output(
            ["yt-dlp", "--get-title", url],
            text=True,
            stderr=subprocess.PIPE,
            **SUBPROCESS_KW,
        ).strip()
        status_q.put(f"Title: {title}")

        folder = out_root / slugify(title)
        folder.mkdir(exist_ok=True)
        status_q.put(f"Output folder: {folder}")

        status_q.put("Downloading video + auto English subtitles...")
        subprocess.run(
            [
                "yt-dlp",
                "--write-auto-subs",
                "--write-subs",
                "--sub-lang", "en.*,en",
                "--convert-subs", "srt",
                "-f", "worst[height>=360]/worst",
                "-o", str(folder / "video.%(ext)s"),
                url,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **SUBPROCESS_KW,
        )

        video_files = [f for f in folder.glob("video.*") if f.suffix in (".mp4", ".webm", ".mkv")]
        srt_files = list(folder.glob("video*.srt"))
        if not video_files:
            raise RuntimeError("yt-dlp finished but no video file was produced.")
        video_file = video_files[0]

        status_q.put(f"Extracting screenshots every {interval}s...")
        shots_dir = folder / "screenshots"
        shots_dir.mkdir(exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-loglevel", "error", "-y",
                "-i", str(video_file),
                "-vf", f"fps=1/{interval}",
                "-q:v", "2",
                str(shots_dir / "shot_%04d.jpg"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **SUBPROCESS_KW,
        )
        shots = sorted(shots_dir.glob("shot_*.jpg"))
        status_q.put(f"Captured {len(shots)} screenshots.")

        entries = list(parse_srt(srt_files[0])) if srt_files else []
        if srt_files:
            status_q.put(f"Parsed {len(entries)} caption lines.")
        else:
            status_q.put("No subtitles found — combined.md will have screenshots only.")

        status_q.put("Writing transcript.txt...")
        if entries:
            plain = "\n".join(text for _, _, text in entries)
            (folder / "transcript.txt").write_text(plain, encoding="utf-8")

        status_q.put("Writing combined.md...")
        md = [f"# {title}", "", f"Source: {url}", ""]
        for i, shot in enumerate(shots):
            start = i * interval
            end = (i + 1) * interval
            chunk = " ".join(t for s, _, t in entries if start <= s < end)
            md.append(f"## [{fmt_time(start)}]")
            md.append("")
            md.append(f"![shot {i+1}](screenshots/{shot.name})")
            md.append("")
            if chunk:
                md.append(chunk)
                md.append("")
        (folder / "combined.md").write_text("\n".join(md), encoding="utf-8")

        status_q.put("Cleaning up source video...")
        video_file.unlink(missing_ok=True)

        status_q.put(f"Done. {len(shots)} screenshots, {len(entries)} caption lines.")
        result_q.put(("ok", folder))

    except FileNotFoundError as e:
        missing = e.filename or str(e)
        result_q.put(("err", f"Required tool not found on PATH: {missing}. "
                             "Install yt-dlp (pip install yt-dlp) and ffmpeg (winget install Gyan.FFmpeg)."))
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr.decode("utf-8", errors="ignore") if isinstance(e.stderr, bytes)
                  else (e.stderr or "")).strip()
        last = stderr.splitlines()[-1] if stderr else f"exit code {e.returncode}"
        result_q.put(("err", f"{Path(e.cmd[0]).name} failed: {last}"))
    except Exception as e:
        result_q.put(("err", f"{type(e).__name__}: {e}"))


# ---------- GUI ----------

class App:
    YT_PATTERN = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Uoink")
        self.root.geometry("600x500")
        self.root.minsize(500, 400)

        self.status_q: queue.Queue = queue.Queue()
        self.result_q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_folder: Path | None = None

        self._build_ui()
        self.root.after(100, self._poll_queues)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True)

        # URL row
        url_row = ttk.Frame(frm)
        url_row.pack(fill="x", **pad)
        ttk.Label(url_row, text="YouTube URL:").pack(side="left")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(url_row, text="Paste from clipboard", command=self._paste).pack(side="left")

        # URL error label (inline)
        self.url_err = ttk.Label(frm, text="", foreground="#b00020")
        self.url_err.pack(fill="x", padx=10)

        # Interval + Extract row
        ctrl_row = ttk.Frame(frm)
        ctrl_row.pack(fill="x", **pad)
        ttk.Label(ctrl_row, text="Screenshot interval (seconds):").pack(side="left")
        self.interval_var = tk.IntVar(value=30)
        self.interval_spin = ttk.Spinbox(
            ctrl_row, from_=5, to=300, textvariable=self.interval_var, width=6
        )
        self.interval_spin.pack(side="left", padx=(8, 16))
        self.extract_btn = ttk.Button(ctrl_row, text="Extract", command=self._on_extract)
        self.extract_btn.pack(side="left")
        self.open_btn = ttk.Button(ctrl_row, text="Open Folder", command=self._open_folder, state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))

        # Progress bar
        self.progress = ttk.Progressbar(frm, mode="indeterminate")
        self.progress.pack(fill="x", **pad)

        # Status log
        log_frame = ttk.LabelFrame(frm, text="Status")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(log_frame, wrap="word", height=12, state="disabled",
                           background="#0e0e10", foreground="#e6e6e6", insertbackground="#e6e6e6")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---- actions ----

    def _paste(self):
        try:
            text = self.root.clipboard_get()
            self.url_var.set(text.strip())
            self.url_err.config(text="")
        except tk.TclError:
            self.url_err.config(text="Clipboard is empty or not text.")

    def _log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _set_busy(self, busy: bool):
        if busy:
            self.extract_btn.config(state="disabled")
            self.open_btn.config(state="disabled")
            self.url_entry.config(state="disabled")
            self.interval_spin.config(state="disabled")
            self.progress.start(12)
        else:
            self.extract_btn.config(state="normal")
            self.url_entry.config(state="normal")
            self.interval_spin.config(state="normal")
            self.progress.stop()

    def _on_extract(self):
        url = self.url_var.get().strip()
        if not self.YT_PATTERN.search(url):
            self.url_err.config(text="URL must contain youtube.com or youtu.be")
            return
        self.url_err.config(text="")

        try:
            interval = int(self.interval_var.get())
        except (tk.TclError, ValueError):
            self.url_err.config(text="Interval must be a whole number.")
            return
        if not (5 <= interval <= 300):
            self.url_err.config(text="Interval must be between 5 and 300 seconds.")
            return

        self.last_folder = None
        self._set_busy(True)
        self._log(f"--- Starting extraction (interval {interval}s) ---")

        self.worker = threading.Thread(
            target=extract,
            args=(url, interval, self.status_q, self.result_q),
            daemon=True,
        )
        self.worker.start()

    def _poll_queues(self):
        try:
            while True:
                msg = self.status_q.get_nowait()
                self._log(msg)
        except queue.Empty:
            pass

        try:
            kind, payload = self.result_q.get_nowait()
            self._set_busy(False)
            if kind == "ok":
                self.last_folder = payload
                self.open_btn.config(state="normal")
                self._log(f"Saved to: {payload}")
                self._notify("Uoink", f"Done — saved to {payload.name}")
            else:
                self._log(f"ERROR: {payload}")
                self._notify("Uoink", f"Failed: {payload}")
        except queue.Empty:
            pass

        self.root.after(150, self._poll_queues)

    def _open_folder(self):
        if self.last_folder and self.last_folder.exists():
            try:
                os.startfile(str(self.last_folder))
            except OSError as e:
                messagebox.showerror("Open Folder", f"Could not open folder: {e}")

    def _notify(self, title: str, body: str):
        if HAVE_TOAST:
            try:
                _toast(title, body, duration="short")
                return
            except Exception:
                pass
        # Fallback: non-blocking-ish messagebox
        try:
            messagebox.showinfo(title, body)
        except Exception:
            pass


def main():
    root = tk.Tk()
    try:
        # Use the modern theme on Windows
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
