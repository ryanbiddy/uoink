"""Build the upload ZIP from an explicit, fail-closed extension file list."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uoink_store import load_store_config

# Review additions explicitly. Never glob new files into a public package.
ALLOWLIST = frozenset("""
background.js
brand/fonts/bungee-OFL.txt
brand/fonts/bungee.woff
brand/fonts/inter-OFL.txt
brand/fonts/inter-italic.woff
brand/fonts/inter.woff
brand/fonts/jetbrains-mono-OFL.txt
brand/fonts/jetbrains-mono.woff
brand/tokens.css
content-reddit.js
content-x-article.js
content.js
icons/icon-128-dark.png
icons/icon-128-light.png
icons/icon-128.png
icons/icon-16-dark.png
icons/icon-16-light.png
icons/icon-16.png
icons/icon-32-dark.png
icons/icon-32-light.png
icons/icon-32.png
icons/icon-48-dark.png
icons/icon-48-light.png
icons/icon-48.png
icons/icon128.png
icons/icon16.png
icons/icon32.png
icons/icon48.png
lib/extract.js
lib/popup-captures.js
lib/store-links.js
lib/ui.js
lib/x-article.js
manifest.json
offscreen.html
offscreen.js
popup.html
popup.js
prompts.json
setup.html
setup.js
store-config.json
uoink-memory.css
uoink-memory.html
uoink-memory.js
""".split())
DEV_ONLY = frozenset({"lib/mock-api.js"})


def build(root: Path = ROOT) -> Path:
    extension = root / "extension"
    files = {p.relative_to(extension).as_posix(): p for p in extension.rglob("*") if p.is_file()}
    links = [p for p in extension.rglob("*") if p.is_symlink() or
             (hasattr(p, "is_junction") and p.is_junction())]
    if links:
        raise ValueError(f"Links are not allowed in the package source: {links}")
    unexpected = set(files) - ALLOWLIST - DEV_ONLY
    missing = ALLOWLIST - set(files)
    if unexpected or missing:
        raise ValueError(f"Extension allowlist mismatch: unexpected={sorted(unexpected)}, missing={sorted(missing)}")
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads(files["manifest.json"].read_text(encoding="utf-8"))
    if manifest.get("version") != version or manifest.get("manifest_version") != 3:
        raise ValueError("Manifest must be MV3 and match VERSION; no version is rewritten")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    load_store_config(files["store-config.json"], strict=True)
    extract = files["lib/extract.js"].read_text(encoding="utf-8")
    if not re.search(r"\bconst USE_MOCK_API = false;", extract):
        raise ValueError("USE_MOCK_API must be false in lib/extract.js")
    payload = {name: files[name].read_bytes() for name in sorted(ALLOWLIST)}
    # CWS assigns/signs the item identity. Retain the key in the source only.
    manifest.pop("key", None)
    payload["manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    for name, data in payload.items():
        if name.endswith((".js", ".html", ".css")):
            text = data.decode("utf-8")
            if "sourceMappingURL=" in text or re.search(r"(?:YOINK_)?USE_MOCK_API\s*=\s*true\b", re.sub(r"//[^\n]*", "", text)):
                raise ValueError(f"Development switch or source map in {name}")
            if re.search(r'''(?:src=["']|importScripts\(["'])[^"']*mock-api''', text):
                raise ValueError(f"Mock API reference in {name}")
            if name.endswith(".html"):
                for ref in re.findall(r'''(?:src|href)=["']([^"'#]+)["']''', text):
                    if ":" in ref or ref.startswith("/"):
                        continue
                    if (Path(name).parent / ref.split("?")[0]).as_posix() not in payload:
                        raise ValueError(f"Missing local asset {ref} in {name}")
    refs = [manifest["background"]["service_worker"], manifest["action"]["default_popup"]]
    refs += list(manifest["icons"].values()) + list(manifest["action"]["default_icon"].values())
    refs += [name for script in manifest.get("content_scripts", []) for name in script.get("js", []) + script.get("css", [])]
    if any(ref not in payload for ref in refs):
        raise ValueError("Manifest references an asset outside the package")
    out = root / "dist" / f"uoink-extension-{version}-cws.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in payload.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    receipt = {"archive": out.name, "bytes": out.stat().st_size, "sha256": digest,
               "version": version, "files": [{"path": n, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                                             for n, b in payload.items()]}
    out.with_suffix(".contents.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    archive = build()
    print(f"{archive}\n{archive.stat().st_size:,} bytes\nSHA-256 {hashlib.sha256(archive.read_bytes()).hexdigest()}")
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            print(f"{item.file_size:>8}  {item.filename}")
