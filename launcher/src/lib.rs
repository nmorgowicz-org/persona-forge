//! Library crate for `persona-forge-launcher`: bundle verification, env bootstrap/retention,
//! and desktop-shell server supervision/health probing
//! (`docs/plans/20260925-native_app_shell_auto_update.md` Phase 2, D9). `main.rs` (the CLI
//! archive's thin bootstrap) and the Tauri desktop shell (Phase 3) both depend on this crate
//! instead of duplicating any of this logic.

pub mod bootstrap;
pub mod health;
pub mod manifest;
pub mod paths;
pub mod retention;
pub mod supervisor;
