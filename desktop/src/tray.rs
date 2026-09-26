//! Tray / menu-bar icon (contract §6.4). Creation failure disables the tray for the session
//! (logged, never a hard error) — `app.rs` calls `build_tray` and treats `Err` that way.

use tauri::image::Image;
use tauri::menu::{Menu, MenuBuilder, MenuItemBuilder};
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::{AppHandle, Runtime};

pub const ID_OPEN: &str = "tray_open";
pub const ID_OPEN_IN_BROWSER: &str = "tray_open_in_browser";
pub const ID_COPY_SERVER_ADDRESS: &str = "tray_copy_server_address";
pub const ID_CHECK_UPDATES: &str = "tray_check_updates";
pub const ID_SHOW_LOGS: &str = "tray_show_logs";
pub const ID_QUIT: &str = "tray_quit";

fn build_tray_menu<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Menu<R>> {
    let open = MenuItemBuilder::with_id(ID_OPEN, "Open Persona Forge").build(app)?;
    let open_in_browser =
        MenuItemBuilder::with_id(ID_OPEN_IN_BROWSER, "Open in Browser").build(app)?;
    let copy_server_address =
        MenuItemBuilder::with_id(ID_COPY_SERVER_ADDRESS, "Copy Server Address").build(app)?;
    let check_updates =
        MenuItemBuilder::with_id(ID_CHECK_UPDATES, "Check for Updates…").build(app)?;
    let show_logs = MenuItemBuilder::with_id(ID_SHOW_LOGS, "Show Logs").build(app)?;
    let quit = MenuItemBuilder::with_id(ID_QUIT, "Quit").build(app)?;
    MenuBuilder::new(app)
        .items(&[
            &open,
            &open_in_browser,
            &copy_server_address,
            &check_updates,
            &show_logs,
            &quit,
        ])
        .build()
}

/// `icon`: the template PNG bytes on macOS (`icon_as_template`), the color mark PNG on
/// Windows/Linux.
pub fn build_tray<R: Runtime>(
    app: &AppHandle<R>,
    icon_bytes: &[u8],
    is_template: bool,
) -> tauri::Result<TrayIcon<R>> {
    let menu = build_tray_menu(app)?;
    let image = Image::from_bytes(icon_bytes)?;
    TrayIconBuilder::new()
        .icon(image)
        .icon_as_template(is_template)
        .menu(&menu)
        .show_menu_on_left_click(true)
        .tooltip("Persona Forge")
        .build(app)
}
