//! Desktop settings persistence (contract §6.7). `<app_data_root>/desktop/settings.json`.

use serde_json::{Map, Value};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const SCHEMA_VERSION: u32 = 1;
const FILENAME: &str = "settings.json";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PortMode {
    Auto,
    Fixed,
}

impl PortMode {
    fn as_str(&self) -> &'static str {
        match self {
            PortMode::Auto => "auto",
            PortMode::Fixed => "fixed",
        }
    }

    fn parse(s: &str) -> Self {
        if s == "fixed" {
            PortMode::Fixed
        } else {
            PortMode::Auto
        }
    }
}

/// GPU acceleration mode (Phase 9, contract D23).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AccelerationMode {
    /// Try the best available accelerator, fall back to CPU on failure.
    Automatic,
    /// Never install or use a GPU env.
    CpuOnly,
    /// Force the NVIDIA (CUDA) path.
    Nvidia,
    /// Force the Intel XPU path.
    IntelXpu,
    /// Force the AMD ROCm path (Linux only).
    Amd,
}

impl Default for AccelerationMode {
    fn default() -> Self {
        AccelerationMode::Automatic
    }
}

/// Last GPU provisioning attempt status (Phase 9).
/// Recorded on every install/probe failure so the user can Retry from Settings
/// without the app silently wasting minutes on a broken install at each launch.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct AccelerationStatus {
    /// The extra that was attempted (e.g., `cuda13`, `xpu`, `rocm`).
    pub extra: String,
    /// The app version the attempt targeted.
    pub version: String,
    /// Error text from the failed step (uv stderr tail or probe message).
    pub error: String,
    /// ISO-8601 UTC timestamp of the attempt.
    pub attempted_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Settings {
    pub port_mode: PortMode,
    pub port: Option<u16>,
    pub network_access: bool,
    pub tray_enabled: bool,
    /// Default `false`; a file without this key reads as `false` (no schema bump, §6.7).
    pub ask_where_to_save: bool,
    /// Phase 9: GPU acceleration mode (default `automatic`).
    pub acceleration: AccelerationMode,
    /// Phase 9: last failed GPU provisioning attempt (`None` = never failed / never tried).
    pub acceleration_status: Option<AccelerationStatus>,
    pub extra: Map<String, Value>,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            port_mode: PortMode::Auto,
            port: None,
            network_access: false,
            tray_enabled: true,
            ask_where_to_save: false,
            acceleration: AccelerationMode::Automatic,
            acceleration_status: None,
            extra: Map::new(),
        }
    }
}

fn settings_path(desktop_dir: &Path) -> PathBuf {
    desktop_dir.join(FILENAME)
}

/// Load settings, applying documented defaults for a missing file. A corrupt file is renamed to
/// `settings.json.bad`, a warning is logged, and defaults are returned — never a boot failure.
pub fn load(desktop_dir: &Path) -> Settings {
    let path = settings_path(desktop_dir);
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return Settings::default(),
    };
    let parsed: Result<Value, _> = serde_json::from_str(&text);
    let Ok(Value::Object(mut obj)) = parsed else {
        let bad_path = desktop_dir.join(format!("{FILENAME}.bad"));
        let _ = fs::rename(&path, &bad_path);
        log::warn!(
            "{} is corrupt; moved to {} and using defaults",
            path.display(),
            bad_path.display()
        );
        return Settings::default();
    };

    let port_mode = obj
        .remove("port_mode")
        .and_then(|v| v.as_str().map(PortMode::parse))
        .unwrap_or(PortMode::Auto);
    let port = obj
        .remove("port")
        .and_then(|v| v.as_u64())
        .and_then(|p| u16::try_from(p).ok())
        .filter(|p| (1024..=65535).contains(p));
    let network_access = obj
        .remove("network_access")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let tray_enabled = obj
        .remove("tray_enabled")
        .and_then(|v| v.as_bool())
        .unwrap_or(true);
    let ask_where_to_save = obj
        .remove("ask_where_to_save")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let acceleration = obj
        .remove("acceleration")
        .and_then(|v| v.as_str().map(|s| s.to_string()))
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or(AccelerationMode::Automatic);
    let acceleration_status = obj
        .remove("acceleration_status")
        .and_then(|v| serde_json::from_value(v).ok());
    obj.remove("schema_version");

    Settings {
        port_mode,
        port,
        network_access,
        tray_enabled,
        ask_where_to_save,
        acceleration,
        acceleration_status,
        extra: obj,
    }
}

/// Validate `port` is in range (1024-65535) before accepting a Settings-window edit.
pub fn is_valid_port(port: u16) -> bool {
    (1024..=65535).contains(&port)
}

/// Atomic write (temp file + rename). Unknown keys in `settings.extra` are preserved.
pub fn save(desktop_dir: &Path, settings: &Settings) -> io::Result<()> {
    fs::create_dir_all(desktop_dir)?;
    let mut obj = settings.extra.clone();
    obj.insert("schema_version".to_string(), Value::from(SCHEMA_VERSION));
    obj.insert(
        "acceleration".to_string(),
        Value::from(serde_json::to_value(settings.acceleration).unwrap_or(Value::String("automatic".into()))),
    );
    obj.insert(
        "acceleration_status".to_string(),
        settings
            .acceleration_status
            .as_ref()
            .map(|s| serde_json::to_value(s).unwrap_or(Value::Null))
            .unwrap_or(Value::Null),
    );
    obj.insert(
        "port_mode".to_string(),
        Value::from(settings.port_mode.as_str()),
    );
    obj.insert(
        "port".to_string(),
        settings.port.map(Value::from).unwrap_or(Value::Null),
    );
    obj.insert(
        "network_access".to_string(),
        Value::from(settings.network_access),
    );
    obj.insert(
        "tray_enabled".to_string(),
        Value::from(settings.tray_enabled),
    );
    obj.insert(
        "ask_where_to_save".to_string(),
        Value::from(settings.ask_where_to_save),
    );

    let path = settings_path(desktop_dir);
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, serde_json::to_string_pretty(&Value::Object(obj))?)?;
    fs::rename(&tmp, &path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_when_the_file_is_missing() {
        let dir = tempfile::tempdir().unwrap();
        let s = load(dir.path());
        assert_eq!(s.port_mode, PortMode::Auto);
        assert_eq!(s.port, None);
        assert!(!s.network_access);
        assert!(s.tray_enabled);
    }

    #[test]
    fn unknown_keys_survive_a_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            dir.path().join("settings.json"),
            r#"{"schema_version":1,"port_mode":"auto","port":8318,"network_access":false,"tray_enabled":true,"future_key":"kept"}"#,
        )
        .unwrap();
        let s = load(dir.path());
        assert_eq!(s.extra.get("future_key"), Some(&Value::from("kept")));

        save(dir.path(), &s).unwrap();
        let reloaded = load(dir.path());
        assert_eq!(reloaded.extra.get("future_key"), Some(&Value::from("kept")));
    }

    #[test]
    fn an_out_of_range_port_is_rejected() {
        assert!(!is_valid_port(80));
        assert!(!is_valid_port(1023));
        assert!(is_valid_port(1024));
        assert!(is_valid_port(65535));
    }

    #[test]
    fn an_out_of_range_persisted_port_is_dropped_on_load() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            dir.path().join("settings.json"),
            r#"{"port_mode":"fixed","port":80}"#,
        )
        .unwrap();
        let s = load(dir.path());
        assert_eq!(s.port, None);
    }

    #[test]
    fn a_corrupt_file_falls_back_to_defaults_and_is_renamed() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("settings.json"), b"{ not json").unwrap();
        let s = load(dir.path());
        assert_eq!(s, Settings::default());
        assert!(dir.path().join("settings.json.bad").is_file());
        assert!(!dir.path().join("settings.json").exists());
    }

    #[test]
    fn ask_where_to_save_defaults_to_false_and_a_file_without_the_key_reads_as_false() {
        let dir = tempfile::tempdir().unwrap();
        assert!(!Settings::default().ask_where_to_save);
        fs::write(
            dir.path().join("settings.json"),
            r#"{"schema_version":1,"port_mode":"auto","port":null,"network_access":false,"tray_enabled":true}"#,
        )
        .unwrap();
        assert!(!load(dir.path()).ask_where_to_save);
    }

    #[test]
    fn save_then_load_round_trips_every_field() {
        let dir = tempfile::tempdir().unwrap();
        let s = Settings {
            port_mode: PortMode::Fixed,
            port: Some(9123),
            network_access: true,
            tray_enabled: false,
            ask_where_to_save: true,
            acceleration: AccelerationMode::Automatic,
            acceleration_status: None,
            extra: Map::new(),
        };
        save(dir.path(), &s).unwrap();
        assert_eq!(load(dir.path()), s);
    }
}
