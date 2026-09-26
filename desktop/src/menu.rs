//! Application menus (contract §6.4). Built with the Tauri menu API; the macOS app menu gets
//! the native About/Hide/Quit, everything else gets a File menu with the same items plus
//! Settings/Check for Updates.

use tauri::menu::{
    AboutMetadataBuilder, Menu, MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder,
};
use tauri::{AppHandle, Runtime};

pub const ID_CHECK_UPDATES: &str = "check_updates";
pub const ID_SETTINGS: &str = "open_settings";
pub const ID_OPEN_IN_BROWSER: &str = "open_in_browser";
pub const ID_COPY_SERVER_ADDRESS: &str = "copy_server_address";
pub const ID_SHOW_LOGS: &str = "show_logs";
pub const ID_DOCUMENTATION: &str = "documentation";
pub const ID_REPORT_ISSUE: &str = "report_issue";
pub const ID_ABOUT_FALLBACK: &str = "about_fallback";

/// Build the full menu bar. `translocation_disabled` (contract §6.9) appends " (disabled —
/// launched outside Applications)" to the Check for Updates title when the user declined the
/// translocation move.
pub fn build_menu<R: Runtime>(
    app: &AppHandle<R>,
    translocation_disabled: bool,
) -> tauri::Result<Menu<R>> {
    // Edit first: WKWebView needs the predefined edit items for clipboard shortcuts to work at
    // all (Phase 1 finding).
    let edit = SubmenuBuilder::new(app, "Edit")
        .undo()
        .redo()
        .separator()
        .cut()
        .copy()
        .paste()
        .select_all()
        .build()?;

    let check_updates_title = if translocation_disabled {
        "Check for Updates… (disabled — move to Applications to enable)"
    } else {
        "Check for Updates…"
    };
    let check_updates = MenuItemBuilder::with_id(ID_CHECK_UPDATES, check_updates_title)
        .enabled(!translocation_disabled)
        .build(app)?;
    let open_in_browser =
        MenuItemBuilder::with_id(ID_OPEN_IN_BROWSER, "Open in Browser").build(app)?;
    let copy_server_address =
        MenuItemBuilder::with_id(ID_COPY_SERVER_ADDRESS, "Copy Server Address").build(app)?;
    let show_logs = MenuItemBuilder::with_id(ID_SHOW_LOGS, "Show Logs").build(app)?;

    // Reload/Actual Size/Zoom/Fullscreen aren't PredefinedMenuItem variants in this Tauri
    // version; wire them with ids the app.rs menu-event handler maps to window/webview calls.
    let reload = MenuItemBuilder::with_id("view_reload", "Reload")
        .accelerator("CmdOrCtrl+R")
        .build(app)?;
    let actual_size = MenuItemBuilder::with_id("view_actual_size", "Actual Size")
        .accelerator("CmdOrCtrl+0")
        .build(app)?;
    let zoom_in = MenuItemBuilder::with_id("view_zoom_in", "Zoom In")
        .accelerator("CmdOrCtrl+Plus")
        .build(app)?;
    let zoom_out = MenuItemBuilder::with_id("view_zoom_out", "Zoom Out")
        .accelerator("CmdOrCtrl+-")
        .build(app)?;
    let fullscreen =
        MenuItemBuilder::with_id("view_fullscreen", "Toggle Full Screen").build(app)?;
    let mut view_builder = SubmenuBuilder::new(app, "View")
        .item(&reload)
        .separator()
        .item(&actual_size)
        .item(&zoom_in)
        .item(&zoom_out)
        .separator()
        .item(&fullscreen);
    if cfg!(debug_assertions) {
        let devtools =
            MenuItemBuilder::with_id("view_devtools", "Toggle Developer Tools").build(app)?;
        view_builder = view_builder.separator().item(&devtools);
    }
    let view = view_builder.build()?;

    let documentation = MenuItemBuilder::with_id(ID_DOCUMENTATION, "Documentation").build(app)?;
    let report_issue = MenuItemBuilder::with_id(ID_REPORT_ISSUE, "Report an Issue").build(app)?;
    let help = SubmenuBuilder::new(app, "Help")
        .item(&documentation)
        .item(&report_issue)
        .build()?;

    if cfg!(target_os = "macos") {
        let about = PredefinedMenuItem::about(
            app,
            None,
            Some(
                AboutMetadataBuilder::new()
                    .name(Some("Persona Forge"))
                    .build(),
            ),
        )?;
        let settings = MenuItemBuilder::with_id(ID_SETTINGS, "Settings…")
            .accelerator("Cmd+,")
            .build(app)?;
        let app_menu = SubmenuBuilder::new(app, "Persona Forge")
            .item(&about)
            .separator()
            .item(&check_updates)
            .item(&settings)
            .separator()
            .item(&PredefinedMenuItem::hide(app, None)?)
            .item(&PredefinedMenuItem::hide_others(app, None)?)
            .item(&PredefinedMenuItem::show_all(app, None)?)
            .separator()
            .item(&PredefinedMenuItem::quit(app, None)?)
            .build()?;
        let file = SubmenuBuilder::new(app, "File")
            .item(&open_in_browser)
            .item(&copy_server_address)
            .item(&show_logs)
            .build()?;
        let window_menu = SubmenuBuilder::new(app, "Window")
            .item(&PredefinedMenuItem::minimize(app, None)?)
            .item(&PredefinedMenuItem::maximize(app, None)?)
            .build()?;
        MenuBuilder::new(app)
            .items(&[&app_menu, &file, &edit, &view, &window_menu, &help])
            .build()
    } else {
        let about =
            MenuItemBuilder::with_id(ID_ABOUT_FALLBACK, "About Persona Forge").build(app)?;
        let settings = MenuItemBuilder::with_id(ID_SETTINGS, "Settings…")
            .accelerator("Ctrl+,")
            .build(app)?;
        let file = SubmenuBuilder::new(app, "File")
            .item(&open_in_browser)
            .item(&copy_server_address)
            .item(&show_logs)
            .separator()
            .item(&settings)
            .item(&check_updates)
            .separator()
            .item(&about)
            .separator()
            .item(&PredefinedMenuItem::quit(app, None)?)
            .build()?;
        MenuBuilder::new(app)
            .items(&[&file, &edit, &view, &help])
            .build()
    }
}
