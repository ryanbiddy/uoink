# Rename the parent folder from yt-extractor to Uoink

After Claude Code exits and the orchestrator script finishes, the parent folder will be auto-renamed by the orchestrator script.

If for any reason that fails, you can rename manually:

1. Close Claude Code, VS Code, any open terminals in this folder, and any text editor with files from this folder open.

2. In a fresh PowerShell window, run:

   ```
   cd C:\Users\hello\OneDrive\Desktop
   Rename-Item -Path "yt-extractor" -NewName "Uoink"
   ```

3. Update any shortcuts, batch files, or environment variables that reference the old path.

4. Restart the Uoink server from the new location:
   ```
   cd C:\Users\hello\OneDrive\Desktop\Uoink
   .\start_server.bat
   ```

5. The extension doesn't need to be reloaded — it talks to the server via HTTP, not the file system.
