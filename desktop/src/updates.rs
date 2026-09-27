//! Native update entry points and periodic update checks (contract §9.3).

use std::time::Duration;

use tauri::{AppHandle, Manager, Runtime};

use crate::app::ManagedState;

const CHECK_INTERVAL: Duration = Duration::from_secs(24 * 60 * 60);

fn checks_disabled<R: Runtime>(app: &AppHandle<R>) -> bool {
    app.try_state::<ManagedState>().is_some_and(|state| {
        state
            .translocation_disabled
            .load(std::sync::atomic::Ordering::SeqCst)
    })
}

/// Starts a launch check once the server reaches Running, then checks every 24 hours.
pub fn schedule_periodic_checks<R: Runtime + 'static>(app: AppHandle<R>) {
    std::thread::spawn(move || {
        loop {
            if app
                .try_state::<ManagedState>()
                .is_some_and(|state| state.bootstrap.lock().ready)
            {
                break;
            }
            std::thread::sleep(Duration::from_secs(1));
        }

        check_in_background(&app);
        loop {
            std::thread::sleep(CHECK_INTERVAL);
            check_in_background(&app);
        }
    });
}

#[cfg(all(target_os = "macos", not(test)))]
fn check_in_background<R: Runtime>(app: &AppHandle<R>) {
    if checks_disabled(app) {
        return;
    }
    use tauri_plugin_sparkle_updater::SparkleUpdaterExt;
    if let Some(updater) = app.sparkle_updater() {
        if let Err(error) = updater.check_for_updates_in_background() {
            log::warn!("background Sparkle update check failed: {error}");
        }
    }
}

#[cfg(all(target_os = "macos", test))]
fn check_in_background<R: Runtime>(_app: &AppHandle<R>) {}

#[cfg(not(target_os = "macos"))]
fn check_in_background<R: Runtime>(app: &AppHandle<R>) {
    if checks_disabled(app) {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_updater::UpdaterExt;
        let result = match app.updater_builder().build() {
            Ok(updater) => updater.check().await,
            Err(error) => {
                log::warn!("updater initialization failed: {error}");
                return;
            }
        };
        match result {
            Ok(Some(update)) => show_consent(&app, update),
            Ok(None) => log::debug!("no desktop update available"),
            Err(error) => log::warn!("background update check failed: {error}"),
        }
    });
}

/// Handles the explicit menu and tray update command.
pub fn check_for_updates<R: Runtime>(app: &AppHandle<R>) {
    if checks_disabled(app) {
        return;
    }
    #[cfg(all(target_os = "macos", not(test)))]
    {
        use tauri_plugin_sparkle_updater::SparkleUpdaterExt;
        match app.sparkle_updater() {
            Some(updater) => {
                if let Err(error) = updater.check_for_updates() {
                    log::warn!("Sparkle update check failed: {error}");
                }
            }
            None => log::warn!("Sparkle updater unavailable outside a macOS app bundle"),
        }
    }
    #[cfg(all(target_os = "macos", test))]
    log::debug!("Sparkle updater is disabled in unit-test builds");
    #[cfg(not(target_os = "macos"))]
    {
        let app = app.clone();
        tauri::async_runtime::spawn(async move {
            use tauri_plugin_updater::UpdaterExt;
            let result = match app.updater_builder().build() {
                Ok(updater) => updater.check().await,
                Err(error) => {
                    log::warn!("updater initialization failed: {error}");
                    return;
                }
            };
            match result {
                Ok(Some(update)) => show_consent(&app, update),
                Ok(None) => show_no_update(&app),
                Err(error) => {
                    log::warn!("update check failed: {error}");
                    show_update_error(&app, &error.to_string());
                }
            }
        });
    }
}

#[cfg(not(target_os = "macos"))]
fn show_consent<R: Runtime>(app: &AppHandle<R>, update: tauri_plugin_updater::Update) {
    use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
    let version = update.version.clone();
    let notes = update
        .body
        .clone()
        .unwrap_or_else(|| "No release notes provided.".into());
    let app = app.clone();
    app.dialog()
        .message(format!("Persona Forge {version} is available.\n\n{notes}"))
        .title("Update Available")
        .buttons(MessageDialogButtons::OkCancelCustom(
            "Install and Relaunch".into(),
            "Later".into(),
        ))
        .show(move |install| {
            if install {
                install_update(app, update);
            }
        });
}

#[cfg(not(target_os = "macos"))]
fn install_update<R: Runtime + 'static>(app: AppHandle<R>, update: tauri_plugin_updater::Update) {
    tauri::async_runtime::spawn(async move {
        let bytes = match update.download(&mut |_chunk, _total| {}, &mut || {}).await {
            Ok(bytes) => bytes,
            Err(error) => {
                log::error!("update download or signature verification failed: {error}");
                show_update_error(&app, &error.to_string());
                return;
            }
        };

        if let Err(error) = stop_server(&app) {
            log::error!("not installing update because server shutdown failed: {error}");
            show_update_error(&app, &error);
            return;
        }
        match update.install(&bytes) {
            Ok(()) => {
                #[cfg(target_os = "linux")]
                app.restart();
                // Windows' NSIS installer exits and relaunches the app itself.
            }
            Err(error) => {
                log::error!("update installation failed: {error}");
                crate::app::resume_after_failed_update(app.clone());
                show_update_error(&app, &error.to_string());
            }
        }
    });
}

#[cfg(any(not(target_os = "macos"), not(test)))]
fn stop_server<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    let state = app.try_state::<ManagedState>().ok_or_else(|| {
        "application state is unavailable; refusing to install the update".to_string()
    })?;
    let pid_file = state.desktop_dir.join("server.pid");
    let mut server = state.server.lock();
    if let Some(handle) = server.as_mut() {
        handle
            .stop(Duration::from_secs(10))
            .map_err(|error| format!("could not stop the embedded server: {error}"))?;
        server.take();
    } else {
        let bootstrap = state.bootstrap.lock();
        if bootstrap.ready {
            return Err(
                "server is marked ready without a managed handle; refusing to install the update"
                    .to_string(),
            );
        }
        if bootstrap.error.is_none() {
            return Err(
                "server bootstrap is still in progress; refusing to install the update".to_string(),
            );
        }
        drop(bootstrap);
        match std::fs::symlink_metadata(&pid_file) {
            Ok(_) => {
                return Err(
                    "server.pid exists without a managed server handle; refusing to install the update"
                        .to_string(),
                );
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!("could not inspect server.pid: {error}"));
            }
        }
    }
    state.port.lock().take();
    {
        let mut bootstrap = state.bootstrap.lock();
        bootstrap.ready = false;
        bootstrap.error = Some("Server stopped for update.".to_string());
    }
    match std::fs::remove_file(&pid_file) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => {
            log::warn!("server stopped but could not remove server.pid: {error}");
        }
    }
    Ok(())
}

#[cfg(not(target_os = "macos"))]
fn show_no_update<R: Runtime>(app: &AppHandle<R>) {
    use tauri_plugin_dialog::DialogExt;
    app.dialog()
        .message("You are using the latest version of Persona Forge.")
        .title("No Updates Available")
        .show(|_| {});
}

#[cfg(not(target_os = "macos"))]
fn show_update_error<R: Runtime>(app: &AppHandle<R>, error: &str) {
    use tauri_plugin_dialog::DialogExt;
    app.dialog()
        .message(format!(
            "Persona Forge could not check or install the update.\n\n{error}"
        ))
        .title("Update Failed")
        .show(|_| {});
}

/// Called when Sparkle commits to applying an update after the application exits.
#[cfg(all(target_os = "macos", not(test)))]
pub fn stop_server_for_sparkle<R: Runtime>(app: &AppHandle<R>) {
    if let Err(error) = stop_server(app) {
        log::error!("could not stop embedded server before Sparkle update: {error}");
    }
}

#[cfg(test)]
mod tests {
    use super::CHECK_INTERVAL;
    use std::time::Duration;

    #[test]
    fn scheduled_update_interval_is_24_hours() {
        assert_eq!(CHECK_INTERVAL, Duration::from_secs(86_400));
    }
}
