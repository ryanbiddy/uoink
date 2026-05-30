use std::process::Command;
use tauri::{Manager, Window};

#[tauri::command]
fn run_inno_silent(install_dir: String) -> Result<String, String> {
    let installer = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .parent()
        .ok_or("could not resolve prototype exe directory")?
        .join("Uoink-Setup-3.1.2.exe");

    if !installer.exists() {
        return Ok(format!(
            "prototype: installer not found at {}; UI flow proved without shelling Inno",
            installer.display()
        ));
    }

    let status = Command::new(installer)
        .arg("/VERYSILENT")
        .arg("/SUPPRESSMSGBOXES")
        .arg("/NORESTART")
        .arg(format!("/DIR={}", install_dir))
        .status()
        .map_err(|e| e.to_string())?;

    if status.success() {
        Ok("installer completed".to_string())
    } else {
        Err(format!("installer exited with status {}", status))
    }
}

#[tauri::command]
fn pick_install_dir() -> Option<String> {
    None
}

#[tauri::command]
fn open_dashboard_window(app: tauri::AppHandle) -> Result<(), String> {
    let url = tauri::WindowUrl::External(
        "http://127.0.0.1:5179/dashboard"
            .parse()
            .map_err(|e| format!("bad dashboard URL: {e}"))?,
    );
    tauri::WindowBuilder::new(&app, "dashboard", url)
        .title("Uoink Dashboard")
        .inner_size(1280.0, 820.0)
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://127.0.0.1:")) {
        return Err("unsupported URL".to_string());
    }
    #[cfg(target_os = "windows")]
    let mut cmd = {
        let mut c = Command::new("cmd");
        c.args(["/C", "start", "", &url]);
        c
    };
    #[cfg(target_os = "macos")]
    let mut cmd = {
        let mut c = Command::new("open");
        c.arg(&url);
        c
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut cmd = {
        let mut c = Command::new("xdg-open");
        c.arg(&url);
        c
    };
    cmd.spawn().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn minimize_window(window: Window) -> Result<(), String> {
    window.minimize().map_err(|e| e.to_string())
}

#[tauri::command]
fn close_window(window: Window) -> Result<(), String> {
    window.close().map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            run_inno_silent,
            pick_install_dir,
            open_dashboard_window,
            open_url,
            minimize_window,
            close_window
        ])
        .run(tauri::generate_context!())
        .expect("error while running Uoink Tauri shell prototype");
}
