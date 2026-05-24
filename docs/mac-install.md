# Uoink — macOS Installation Guide

Uoink is a local-first helper for AI-assisted YouTube research. This guide walks through installing, configuring, and troubleshooting the macOS version of Uoink.

---

## 1. What You'll Install

Uoink consists of two components:
1. **Chrome Extension:** The frontend user interface that displays in-page "Uoink" buttons, previews corpora, controls settings, and opens Uoink Memory.
2. **macOS Helper App (`Uoink.app`):** A background helper packaged as a `.dmg` installer. The helper runs a local server (`127.0.0.1:5179`), manages yt-dlp, extracts transcripts, handles screenshot capture, runs the optional local Anthropic AI pipelines, and persists your library using a local SQLite index.

The architecture is identical to the Windows version, replacing Windows-specific packaging (Inno Setup) with a macOS `.dmg` and LaunchAgent.

---

## 2. System Requirements

* **Operating System:** macOS 12 (Monterey) or later.
* **Architecture:** Intel (x86_64) or Apple Silicon (M1/M2/M3/M4, arm64). The app is packaged as a universal binary and runs natively on both platforms.
* **Browser:** Google Chrome (or any Chromium-based browser supporting Manifest V3, such as Brave, Edge, Opera, or Arc).

---

## 3. Installation Steps

Follow these steps to get Uoink up and running on your Mac:

### Step 1: Install the Chrome Extension
1. Open Google Chrome.
2. Visit the Chrome Web Store and search for **Uoink**.
3. Click **Add to Chrome** to install the extension.

### Step 2: Download and Install the Helper App
1. Download the latest `Uoink-Setup-2.1.0.dmg` from the official release page.
2. Double-click the downloaded `.dmg` file to mount it.
3. Drag the **Uoink** icon into your **Applications** folder.
4. Eject the `.dmg` installer.

### Step 3: Run the Helper App
1. Open your **Applications** folder and double-click **Uoink**.
2. **Gatekeeper Notice:** Because the helper runs a local web server, macOS Gatekeeper may ask you to confirm launching the application. Click **Open** to proceed.
3. On first run, Uoink automatically configures a background user agent (`LaunchAgent`) to ensure the server starts automatically whenever you log in.
4. You will see a small status check on the Extension Setup Page. When the status indicator turns green, the helper is successfully running in the background.

---

## 4. Where Uoink Stores Data

Uoink is local-first. All metadata, indexes, and extracted content reside on your local disk.

* **Uoinked Corpora:** `~/Desktop/Uoink/`
  Your raw text transcripts, metadata JSONs, inlined screenshots, and thumbnails are organized into subfolders by topic inside this directory.
* **Helper Application Support:** `~/Library/Application Support/Uoink/`
  This folder contains the internal runtime files:
  * `index.db`: The SQLite database containing your library index (FTS5 search), queue, and hook taxonomy data.
  * `token.txt`: The randomly generated access token used to secure requests between the extension and helper.
  * `server.log`: The diagnostic log file containing the background server's operations.
  * `server.pid`: The process ID file of the running background helper.
  * `jobs.json.migrated` / `taxonomy.json.migrated`: Legacy backups migrated from Uoink v1.0.

---

## 5. Anthropic API Key Storage

If you choose to enable the optional AI-powered features (Comment Intelligence, Hook Type classification, or Entity Extraction), you must supply your own Anthropic API key.

To protect your API key, macOS Uoink stores it in the **macOS Keychain** using the standard Python `keyring` library:
* **Service Name:** `Uoink`
* **Account/Username:** `anthropic_key`

The helper reads this key from the Keychain only when making API requests directly to Anthropic's endpoints. It is never stored in plaintext within settings files, and the `/settings` HTTP endpoint never returns the key.

---

## 6. Uninstalling Uoink

To fully remove Uoink and all associated data from your Mac:

1. **Remove the Chrome Extension:** Right-click the Uoink extension icon in your Chrome toolbar and select **Remove from Chrome...**
2. **Delete the Helper App:** Open `/Applications/` and drag **Uoink.app** to the Trash. The background helper process will automatically terminate.
3. **Remove Auto-Start LaunchAgent:** Delete the LaunchAgent configuration file:
   ```bash
   rm ~/Library/LaunchAgents/com.ryanbiddy.uoink.plist
   ```
4. **Delete Application Support (Optional):** To remove the SQLite index database, diagnostic logs, and security tokens:
   ```bash
   rm -rf ~/Library/Application\ Support/Uoink/
   ```
5. **Delete Output Folder (Optional):** To delete all previously extracted video folders:
   ```bash
   rm -rf ~/Desktop/Uoink/
   ```

---

## 7. Troubleshooting

### "Helper Not Running" Warning
If the Chrome extension popup shows an orange status indicator:
1. Verify that **Uoink.app** is inside your `/Applications/` folder.
2. Manually launch the application by double-clicking it in Finder.
3. Open Terminal and check if the helper is listening on port 5179:
   ```bash
   lsof -i :5179
   ```
4. If another process is using port 5179, you must free up the port or terminate the conflicting service before starting Uoink.

### Gatekeeper Blocked Launch
If macOS refuses to open the app with a message that it "cannot be opened because the developer cannot be verified":
1. Open **System Settings** (or **System Preferences**).
2. Go to **Privacy & Security**.
3. Scroll down to the **Security** section.
4. Under the blocked app notification, click **Open Anyway** and enter your macOS administrator password to authorize execution.

### Keychain Prompt on First Run
Upon first launching an AI extraction, macOS may display a system prompt asking: *"Uoink wants to access key 'anthropic_key' in your keychain."*
* Click **Always Allow** to permit the background helper to retrieve the Anthropic API key during extractions without repeatedly prompting you.
