"""Installed Darwin menu bar. AppKit creation, callbacks and run loop stay on main."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import queue
import sys
import threading
import urllib.request
import webbrowser

from helper import mac_ui
from uoink_tray import UoinkTray

log = logging.getLogger("uoink.menubar")


def single_instance(data_root: Path):
    import fcntl
    data_root.mkdir(parents=True, exist_ok=True)
    # Keep the inode in place. Unlinking a flock file permits two live locks.
    stream = (data_root / "menubar.lock").open("a+b")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        return None
    return stream


class MenuClient(UoinkTray):
    def post(self, path, body):
        request = urllib.request.Request(self._base + path, data=json.dumps(body).encode(),
                                         headers={"X-Uoink-Token": self._token(),
                                                  "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return json.load(response)
        except Exception:
            return None

    def dashboard(self, settings=False):
        url = self.dashboard_url + ("#settings" if settings else "")
        result = self.post("/helper/dashboard", {"settings": settings})
        if not result or not result.get("ok"):
            webbrowser.open(url)

    def folder(self):
        # Settings may have changed since this process started.
        data, _ = self._get("/settings", auth=True)
        path = (data or {}).get("settings", {}).get("output_dir") or self.output_dir
        self._open_path(Path(path))


def run_menu(client: MenuClient) -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("AppKit must run on the process main thread")
    import AppKit as A
    from Foundation import NSObject, NSTimer, NSRunLoop, NSRunLoopCommonModes

    app = A.NSApplication.sharedApplication()
    app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)
    updates = queue.Queue()
    running = threading.Event()
    stopping = threading.Event()
    paths = []

    class Actions(NSObject):
        def dashboard_(self, sender):
            threading.Thread(target=client.dashboard, daemon=True).start()

        def settings_(self, sender):
            threading.Thread(target=lambda: client.dashboard(settings=True), daemon=True).start()

        def folder_(self, sender):
            threading.Thread(target=client.folder, daemon=True).start()

        def recent_(self, sender):
            index = sender.tag()
            if 0 <= index < len(paths) and paths[index]:
                client._open_path(Path(paths[index]))

        def quit_(self, sender):
            # Do not remove the icon on a failed request: the user can retry.
            def quit_helper():
                result = client.post("/helper/quit", {})
                if not result or not result.get("ok"):
                    updates.put(("Uoink: Quit failed. Try again.", None))
            threading.Thread(target=quit_helper, daemon=True).start()

        def tick_(self, timer):
            running.set()  # Connection is reported only after the event loop runs.
            try:
                while True:
                    title, recent = updates.get_nowait()
                    status.setTitle_(title)
                    if recent is not None:
                        recent_menu.removeAllItems()
                        paths[:] = [row.get("folder") or row.get("path") for row in recent]
                        for index, row in enumerate(recent):
                            item = add(recent_menu, (row.get("title") or row.get("slug") or "Untitled")[:48], "recent:")
                            item.setTag_(index)
                        if not recent:
                            add(recent_menu, "No recent items yet", None)
            except queue.Empty:
                pass

    actions = Actions.alloc().init()

    def add(menu, title, selector):
        item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setTarget_(actions)
        item.setEnabled_(selector is not None)
        menu.addItem_(item)
        return item

    status_item = A.NSStatusBar.systemStatusBar().statusItemWithLength_(A.NSVariableStatusItemLength)
    image = A.NSImage.alloc().initWithSize_((18, 18))
    assets = Path(__file__).resolve().parents[1] / "assets/brand"
    for name in ("menubar-template.png", "menubar-template@2x.png"):
        representation = A.NSBitmapImageRep.imageRepWithContentsOfFile_(str(assets / name))
        if representation is None:
            raise RuntimeError("Missing menu-bar template: " + name)
        representation.setSize_((18, 18))
        image.addRepresentation_(representation)
    image.setTemplate_(True)
    status_item.button().setImage_(image)
    status_item.button().setToolTip_("Uoink " + client.version)
    menu = A.NSMenu.alloc().init()
    menu.setAutoenablesItems_(False)
    status = add(menu, "Uoink: Connecting...", None)
    menu.addItem_(A.NSMenuItem.separatorItem())
    add(menu, "Open dashboard", "dashboard:")
    add(menu, "Open folder", "folder:")
    add(menu, "Settings", "settings:")
    recent_menu = A.NSMenu.alloc().init()
    recent_menu.setAutoenablesItems_(False)
    recent_item = add(menu, "Recent items", None)
    recent_item.setEnabled_(True)
    recent_item.setSubmenu_(recent_menu)
    menu.addItem_(A.NSMenuItem.separatorItem())
    add(menu, "Quit Uoink", "quit:")
    status_item.setMenu_(menu)
    timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(0.25, actions, "tick:", None, True)
    NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)

    def poll():
        running.wait()
        connected = False
        while not stopping.is_set():
            if not connected:
                response = client.post("/helper/ui", {"pid": os.getpid()})
                connected = bool(response and response.get("ok"))
                if connected:
                    log.info("menu bar connected (pid %s)", os.getpid())
            client._refresh_status()
            client._refresh_recent()
            updates.put((client._status_text(), list(client._recent)))
            stopping.wait(5)

    threading.Thread(target=poll, name="uoink-menu-http", daemon=True).start()
    try:
        app.run()
    finally:
        stopping.set()
        timer.invalidate()
        A.NSStatusBar.systemStatusBar().removeStatusItem_(status_item)


def main() -> int:
    if sys.platform != "darwin":
        return 1
    mac_ui.watch_parent()
    import uoink_install_isolation as isolation
    isolation.apply_from_process()
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, choices=["127.0.0.1"])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--token-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    lock = single_instance(args.data_root)
    if lock is None:
        return 0
    logging.basicConfig(level=logging.INFO)
    client = MenuClient(host=args.host, port=args.port, version=args.version,
                        token_path=args.token_path, output_dir=args.output_dir,
                        dashboard_url=f"http://{args.host}:{args.port}/dashboard", stop_callback=lambda: None)
    try:
        run_menu(client)
    finally:
        mac_ui.close_children()
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
