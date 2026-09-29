//! GPU family detection for native launcher (Phase 9 Task 2).
//!
//! Mirrors the rules in `src/persona_forge/gpu_family.py` exactly, so Python and Rust
//! cannot drift. Platform-specific probes read PCI vendor IDs, device nodes, and run
//! `nvidia-smi`. The CUDA 12/13 selection rule (D23) is: compute capability ≥ (7,5)
//! **and** driver CUDA major ≥ 13 → `cuda13`; otherwise → `cuda12`.
//!
//! # Test vectors
//!
//! Shared JSON fixture at `tests/fixtures/gpu_family_cases.json` is read by both the
//! Python tests (`test_gpu_family.py`) and Rust tests (`gpu.rs`), so the detection
//! logic stays in lockstep across languages.

#[cfg(target_os = "linux")]
use std::path::Path;
use std::process::Command;

/// Acceleration family (contract D23).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Accel {
    /// CPU-only (default; macOS, no GPU, or AMD on Windows).
    Cpu,
    /// NVIDIA CUDA 12 (cu126 torch build).
    Cuda12,
    /// NVIDIA CUDA 13 (cu130 torch build).
    Cuda13,
    /// Intel Arc/Intel iGPU (xpu torch build).
    IntelXpu,
    /// AMD ROCm (Linux only; Windows falls back to CPU).
    Rocm,
}

/// Operating system abstraction for probe selection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Os {
    Linux,
    Windows,
    Macos,
}

/// Injectable GPU probes — unit-testable without hardware.
///
/// Each method corresponds to a probe in `gpu_family.py`:
/// - `nvidia_pci`: PCI vendor ID `0x10de` in `/sys/bus/pci/devices/*/vendor`
/// - `cuda_device_node`: `/dev/nvidia*` glob
/// - `nvidia_smi`: successful `nvidia-smi --query-gpu=driver_version` run
/// - `amd_pci`: PCI vendor ID `0x1002`
/// - `rocm_device_node`: `/dev/kfd` presence
/// - `intel_pci`: PCI vendor ID `0x8086`
/// - `intel_device_node`: `/dev/dri/renderD*` glob
///
/// `compute_capability` and `driver_cuda_major` are used for the D23 CUDA build selection
/// (see `select_cuda_extra`).
pub trait GpuProbe {
    /// NVIDIA PCI vendor ID present (Linux: `/sys/bus/pci/devices/*/vendor`).
    fn nvidia_pci_present(&self) -> bool;
    /// `/dev/nvidia*` device node exists.
    fn cuda_device_node_present(&self) -> bool;
    /// `nvidia-smi` runs successfully and reports a driver version.
    /// This is the cross-platform NVIDIA capability signal (Linux + Windows).
    fn nvidia_smi_capable(&self) -> bool;
    /// AMD PCI vendor ID present.
    fn amd_pci_present(&self) -> bool;
    /// `/dev/kfd` (ROCm kernel interface) exists.
    fn rocm_device_node_present(&self) -> bool;
    /// Intel PCI vendor ID present.
    fn intel_pci_present(&self) -> bool;
    /// `/dev/dri/renderD*` device node exists.
    fn intel_device_node_present(&self) -> bool;
    /// GPU compute capability as `(major, minor)` from `nvidia-smi --query-gpu=compute_cap`.
    /// `None` if unavailable or not an NVIDIA GPU.
    fn compute_capability(&self) -> Option<(u32, u32)>;
    /// Driver's supported CUDA major version from `nvidia-smi` output.
    /// `None` if unavailable.
    fn driver_cuda_major(&self) -> Option<u32>;
}

/// Platform-native probe implementation.
pub struct PlatformProbe;

impl GpuProbe for PlatformProbe {
    #[cfg(target_os = "linux")]
    fn nvidia_pci_present(&self) -> bool {
        pci_vendor_present("/sys/bus/pci/devices", "0x10de")
    }

    #[cfg(not(target_os = "linux"))]
    fn nvidia_pci_present(&self) -> bool {
        false
    }

    #[cfg(target_os = "linux")]
    fn cuda_device_node_present(&self) -> bool {
        glob_any("/dev/nvidia*")
    }

    #[cfg(not(target_os = "linux"))]
    fn cuda_device_node_present(&self) -> bool {
        false
    }

    fn nvidia_smi_capable(&self) -> bool {
        nvidia_smi_driver_version().is_ok()
    }

    #[cfg(target_os = "linux")]
    fn amd_pci_present(&self) -> bool {
        pci_vendor_present("/sys/bus/pci/devices", "0x1002")
    }

    #[cfg(not(target_os = "linux"))]
    fn amd_pci_present(&self) -> bool {
        false
    }

    #[cfg(target_os = "linux")]
    fn rocm_device_node_present(&self) -> bool {
        Path::new("/dev/kfd").exists()
    }

    #[cfg(not(target_os = "linux"))]
    fn rocm_device_node_present(&self) -> bool {
        false
    }

    #[cfg(target_os = "linux")]
    fn intel_pci_present(&self) -> bool {
        pci_vendor_present("/sys/bus/pci/devices", "0x8086")
    }

    #[cfg(target_os = "windows")]
    fn intel_pci_present(&self) -> bool {
        windows_intel_adapter_present()
    }

    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    fn intel_pci_present(&self) -> bool {
        false
    }

    #[cfg(target_os = "linux")]
    fn intel_device_node_present(&self) -> bool {
        glob_any("/dev/dri/renderD*")
    }

    #[cfg(target_os = "windows")]
    fn intel_device_node_present(&self) -> bool {
        windows_intel_adapter_present()
    }

    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    fn intel_device_node_present(&self) -> bool {
        false
    }

    fn compute_capability(&self) -> Option<(u32, u32)> {
        nvidia_smi_compute_cap().ok()
    }

    fn driver_cuda_major(&self) -> Option<u32> {
        nvidia_smi_cuda_version().ok()
    }
}

/// Detect the accelerator family using injectable probes.
///
/// Priority: NVIDIA (cuda) > AMD (rocm, Linux only) > Intel (intel-xpu).
/// macOS always returns `Cpu` (default torch wheel includes MPS).
///
/// For NVIDIA, applies the D23 CUDA build selection rule:
/// compute capability ≥ (7,5) AND driver CUDA major ≥ 13 → `Cuda13`, else `Cuda12`.
pub fn detect(p: &dyn GpuProbe, os: Os) -> Accel {
    // macOS is CPU for this manifest (default torch wheel already includes MPS).
    if os == Os::Macos {
        return Accel::Cpu;
    }

    // NVIDIA: highest priority. Check PCI presence (Linux) or nvidia-smi (cross-platform).
    // PCI present requires the device node for capability; nvidia-smi success is itself the
    // capability signal (Windows case, where /dev/nvidia* doesn't exist).
    if p.nvidia_pci_present() {
        // Linux: PCI found. Check device node for capability.
        if p.cuda_device_node_present() {
            let cc = p.compute_capability();
            let driver_major = p.driver_cuda_major();
            return select_cuda_extra(cc, driver_major);
        }
        // PCI present but no device node: not capable, fall through to CPU.
    } else if p.nvidia_smi_capable() {
        // nvidia-smi works (Windows or no PCI but nvidia-smi installed).
        let cc = p.compute_capability();
        let driver_major = p.driver_cuda_major();
        return select_cuda_extra(cc, driver_major);
    }

    // AMD: ROCm is Linux-only (contract D23). On Windows/macOS, AMD GPUs fall back to CPU.
    if p.amd_pci_present() && p.rocm_device_node_present() {
        return Accel::Rocm;
    }

    // Intel: Arc and iGPUs with compute support.
    if p.intel_pci_present() && p.intel_device_node_present() {
        return Accel::IntelXpu;
    }

    Accel::Cpu
}

/// Apply the D23 CUDA build selection rule.
///
/// Returns `Cuda13` when compute capability ≥ (7,5) **and** driver CUDA major ≥ 13;
/// otherwise returns `Cuda12`. Unknowns (`None`) default to `Cuda12` (conservative).
pub fn select_cuda_extra(
    compute_capability: Option<(u32, u32)>,
    driver_cuda_major: Option<u32>,
) -> Accel {
    if let (Some(cc), Some(major)) = (compute_capability, driver_cuda_major) {
        if (cc.0 > 7 || (cc.0 == 7 && cc.1 >= 5)) && major >= 13 {
            return Accel::Cuda13;
        }
    }
    Accel::Cuda12
}

/// Check if a PCI vendor ID is present in `/sys/bus/pci/devices/*/vendor`.
///
/// Returns `true` if any device file matches the given vendor ID string (e.g., `"0x10de"`).
#[cfg(target_os = "linux")]
fn pci_vendor_present(base: &str, vendor_id: &str) -> bool {
    let base_path = Path::new(base);
    let entries = match std::fs::read_dir(base_path) {
        Ok(e) => e,
        Err(_) => return false,
    };
    for entry in entries.flatten() {
        let vendor_path = entry.path().join("vendor");
        if let Ok(vendor) = std::fs::read_to_string(vendor_path) {
            if vendor.trim() == vendor_id {
                return true;
            }
        }
    }
    false
}

/// Return `true` if any path matches the given glob pattern.
///
/// Simplified glob: only supports trailing `*` wildcard.
#[cfg(target_os = "linux")]
fn glob_any(pattern: &str) -> bool {
    let star_idx = match pattern.rfind('*') {
        Some(i) => i,
        None => return false,
    };
    let prefix = Path::new(&pattern[..star_idx]);
    let Some(parent) = prefix.parent() else {
        return false;
    };
    let Some(name_prefix) = prefix.file_name() else {
        return false;
    };
    match std::fs::read_dir(parent) {
        Ok(entries) => entries.flatten().any(|entry| {
            entry
                .file_name()
                .to_string_lossy()
                .starts_with(name_prefix.to_string_lossy().as_ref())
        }),
        Err(_) => false,
    }
}

#[cfg(target_os = "windows")]
fn windows_intel_adapter_present() -> bool {
    use windows::Win32::Graphics::Gdi::{EnumDisplayDevicesW, DISPLAY_DEVICEW};

    let mut index = 0;
    loop {
        let mut device = DISPLAY_DEVICEW {
            cb: std::mem::size_of::<DISPLAY_DEVICEW>() as u32,
            ..Default::default()
        };
        if !unsafe { EnumDisplayDevicesW(None, index, &mut device, 0) }.as_bool() {
            return false;
        }
        let id_end = device
            .DeviceID
            .iter()
            .position(|&ch| ch == 0)
            .unwrap_or(device.DeviceID.len());
        let id = String::from_utf16_lossy(&device.DeviceID[..id_end]);
        if id.to_ascii_uppercase().contains("VEN_8086") {
            return true;
        }
        index += 1;
    }
}

/// Run `nvidia-smi --query-gpu=driver_version --format=csv,noheader` and return the output.
///
/// This is the cross-platform NVIDIA capability signal.
fn nvidia_smi_driver_version() -> Result<String, String> {
    let output = Command::new("nvidia-smi")
        .arg("--query-gpu=driver_version")
        .arg("--format=csv,noheader")
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

/// Parse `nvidia-smi --query-gpu=compute_cap` into `(major, minor)`.
fn nvidia_smi_compute_cap() -> Result<(u32, u32), String> {
    let output = Command::new("nvidia-smi")
        .arg("--query-gpu=compute_cap")
        .arg("--format=csv,noheader")
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let text = text.trim();
    let mut parts = text.split('.');
    let major = parts
        .next()
        .and_then(|s| s.parse::<u32>().ok())
        .ok_or_else(|| format!("invalid compute_cap: {text}"))?;
    let minor = parts
        .next()
        .and_then(|s| s.parse::<u32>().ok())
        .unwrap_or(0);
    Ok((major, minor))
}

/// Parse the `CUDA Version: X.Y` line from `nvidia-smi` output and return the major version.
///
/// This is the driver's supported CUDA version (not the installed toolkit).
fn nvidia_smi_cuda_version() -> Result<u32, String> {
    let output = Command::new("nvidia-smi")
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }
    let text = String::from_utf8_lossy(&output.stdout);
    // Find "CUDA Version: X.Y" or "CUDA Version : X.Y" (format varies by locale/version).
    let idx = text
        .find("CUDA Version")
        .ok_or("CUDA Version line not found")?;
    let after = &text[idx + "CUDA Version".len()..];
    // Skip whitespace and colons
    let after = after.trim_start_matches(|c: char| c.is_whitespace() || c == ':');
    // Extract the number before the dot or space
    let num: String = after
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == '.')
        .collect();
    let major: u32 = num
        .split('.')
        .next()
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| format!("invalid CUDA version: {num}"))?;
    Ok(major)
}

/// Convenience function using the platform-native probes.
pub fn detect_platform() -> Accel {
    let probe = PlatformProbe;
    let os = if cfg!(target_os = "linux") {
        Os::Linux
    } else if cfg!(target_os = "windows") {
        Os::Windows
    } else {
        Os::Macos
    };
    detect(&probe, os)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json;
    use std::fs;

    /// Fake probe for unit tests.
    struct FakeProbe {
        nvidia_pci: bool,
        cuda_node: bool,
        nvidia_smi: bool,
        amd_pci: bool,
        rocm_node: bool,
        intel_pci: bool,
        intel_node: bool,
        cc: Option<(u32, u32)>,
        driver_major: Option<u32>,
    }

    impl GpuProbe for FakeProbe {
        fn nvidia_pci_present(&self) -> bool {
            self.nvidia_pci
        }
        fn cuda_device_node_present(&self) -> bool {
            self.cuda_node
        }
        fn nvidia_smi_capable(&self) -> bool {
            self.nvidia_smi
        }
        fn amd_pci_present(&self) -> bool {
            self.amd_pci
        }
        fn rocm_device_node_present(&self) -> bool {
            self.rocm_node
        }
        fn intel_pci_present(&self) -> bool {
            self.intel_pci
        }
        fn intel_device_node_present(&self) -> bool {
            self.intel_node
        }
        fn compute_capability(&self) -> Option<(u32, u32)> {
            self.cc
        }
        fn driver_cuda_major(&self) -> Option<u32> {
            self.driver_major
        }
    }

    fn run_case(
        nvidia_pci: bool,
        cuda_node: bool,
        nvidia_smi: bool,
        amd_pci: bool,
        rocm_node: bool,
        intel_pci: bool,
        intel_node: bool,
        cc: Option<(u32, u32)>,
        driver_major: Option<u32>,
        os: Os,
    ) -> Accel {
        let probe = FakeProbe {
            nvidia_pci,
            cuda_node,
            nvidia_smi,
            amd_pci,
            rocm_node,
            intel_pci,
            intel_node,
            cc,
            driver_major,
        };
        detect(&probe, os)
    }

    #[test]
    fn test_cuda13_selection() {
        // RTX 5090: CC (12, 0), driver CUDA 13
        let result = run_case(
            true,
            true,
            true, // NVIDIA present
            false,
            false, // no AMD
            false,
            false, // no Intel
            Some((12, 0)),
            Some(13),
            Os::Linux,
        );
        assert_eq!(result, Accel::Cuda13);
    }

    #[test]
    fn test_cuda12_selection() {
        // Older GPU: CC (6, 1) (Pascal), driver CUDA 13
        let result = run_case(
            true,
            true,
            true,
            false,
            false,
            false,
            false,
            Some((6, 1)),
            Some(13),
            Os::Linux,
        );
        assert_eq!(result, Accel::Cuda12);
    }

    #[test]
    fn test_cuda12_with_old_driver() {
        // RTX 5090 but driver only supports CUDA 12.6
        let result = run_case(
            true,
            true,
            true,
            false,
            false,
            false,
            false,
            Some((12, 0)),
            Some(12),
            Os::Linux,
        );
        assert_eq!(result, Accel::Cuda12);
    }

    #[test]
    fn test_cuda12_pci_present_no_device_node() {
        // PCI present but no device node: not capable, falls back to CPU.
        // This matches Python's resolve_gpu_family: present without capability = cpu.
        let result = run_case(
            true,
            false,
            true, // PCI present, no device node, nvidia-smi works
            false,
            false,
            false,
            false,
            None,
            Some(13),
            Os::Linux,
        );
        assert_eq!(result, Accel::Cpu);
    }

    #[test]
    fn test_rocm_selection() {
        // AMD GPU on Linux
        let result = run_case(
            false,
            false,
            false, // no NVIDIA
            true,
            true, // AMD PCI + /dev/kfd
            false,
            false, // no Intel
            None,
            None,
            Os::Linux,
        );
        assert_eq!(result, Accel::Rocm);
    }

    #[test]
    fn test_intel_xpu_selection() {
        // Intel GPU
        let result = run_case(
            false,
            false,
            false,
            false,
            false,
            true,
            true, // Intel PCI + /dev/dri/renderD*
            None,
            None,
            Os::Linux,
        );
        assert_eq!(result, Accel::IntelXpu);
    }

    #[test]
    fn test_macos_always_cpu() {
        // Even with NVIDIA PCI present, macOS is CPU
        let result = run_case(
            true,
            true,
            true,
            false,
            false,
            false,
            false,
            Some((12, 0)),
            Some(13),
            Os::Macos,
        );
        assert_eq!(result, Accel::Cpu);
    }

    #[test]
    fn test_priority_cuda_over_others() {
        // NVIDIA should win over AMD and Intel
        let result = run_case(
            true,
            true,
            true, // NVIDIA
            true,
            true, // AMD
            true,
            true, // Intel
            Some((12, 0)),
            Some(13),
            Os::Linux,
        );
        assert_eq!(result, Accel::Cuda13);
    }

    #[test]
    fn test_nvidia_smi_alone_is_cuda() {
        // Windows case: nvidia-smi works but no sysfs probes
        let result = run_case(
            false,
            false,
            true, // only nvidia-smi
            false,
            false,
            false,
            false,
            Some((12, 0)),
            Some(13),
            Os::Windows,
        );
        assert_eq!(result, Accel::Cuda13);
    }

    #[test]
    fn test_pci_present_but_no_device_node() {
        // PCI present but no device node and no nvidia-smi: not capable
        let result = run_case(
            true,
            false,
            false, // PCI only
            false,
            false,
            false,
            false,
            None,
            None,
            Os::Linux,
        );
        assert_eq!(result, Accel::Cpu);
    }

    #[test]
    fn test_no_hardware_is_cpu() {
        let result = run_case(
            false,
            false,
            false,
            false,
            false,
            false,
            false,
            None,
            None,
            Os::Linux,
        );
        assert_eq!(result, Accel::Cpu);
    }

    #[test]
    fn test_select_cuda_extra_rule() {
        // D23 rule: CC >= (7,5) AND driver >= 13 -> cuda13
        assert_eq!(select_cuda_extra(Some((12, 0)), Some(13)), Accel::Cuda13);
        assert_eq!(select_cuda_extra(Some((8, 6)), Some(13)), Accel::Cuda13);
        assert_eq!(select_cuda_extra(Some((7, 5)), Some(13)), Accel::Cuda13);
        assert_eq!(select_cuda_extra(Some((7, 5)), Some(12)), Accel::Cuda12);
        assert_eq!(select_cuda_extra(Some((6, 1)), Some(13)), Accel::Cuda12);
        assert_eq!(select_cuda_extra(Some((12, 0)), Some(12)), Accel::Cuda12);
        assert_eq!(select_cuda_extra(None, Some(13)), Accel::Cuda12);
        assert_eq!(select_cuda_extra(Some((12, 0)), None), Accel::Cuda12);
        assert_eq!(select_cuda_extra(None, None), Accel::Cuda12);
    }

    /// Load shared test vectors from `tests/fixtures/gpu_family_cases.json`.
    ///
    /// This ensures Python and Rust cannot drift.
    #[test]
    fn test_shared_fixture_vectors() {
        let fixture_path = "../tests/fixtures/gpu_family_cases.json";
        let content = fs::read_to_string(fixture_path)
            .expect("shared fixture tests/fixtures/gpu_family_cases.json should exist");
        let cases: Vec<serde_json::Value> =
            serde_json::from_str(&content).expect("fixture should be valid JSON");

        for case in &cases {
            let name = case["name"].as_str().expect("case name");
            let nvidia_pci = case["nvidia_pci"].as_bool().unwrap();
            let cuda_node = case["cuda_node"].as_bool().unwrap();
            let nvidia_smi = case["nvidia_smi"].as_bool().unwrap();
            let amd_pci = case["amd_pci"].as_bool().unwrap();
            let rocm_node = case["rocm_node"].as_bool().unwrap();
            let intel_pci = case["intel_pci"].as_bool().unwrap();
            let intel_node = case["intel_node"].as_bool().unwrap();
            let cc: Option<(u32, u32)> = case["compute_capability"]
                .as_array()
                .map(|a| (a[0].as_u64().unwrap() as u32, a[1].as_u64().unwrap() as u32));
            let driver_major: Option<u32> = case["driver_cuda_major"].as_u64().map(|n| n as u32);
            let os = match case["os"].as_str().unwrap() {
                "linux" => Os::Linux,
                "windows" => Os::Windows,
                "macos" => Os::Macos,
                other => panic!("unknown os: {other}"),
            };
            let expected = match case["expected"].as_str().unwrap() {
                "cpu" => Accel::Cpu,
                "cuda12" => Accel::Cuda12,
                "cuda13" => Accel::Cuda13,
                "intel-xpu" => Accel::IntelXpu,
                "rocm" => Accel::Rocm,
                other => panic!("unknown expected: {other}"),
            };

            let result = run_case(
                nvidia_pci,
                cuda_node,
                nvidia_smi,
                amd_pci,
                rocm_node,
                intel_pci,
                intel_node,
                cc,
                driver_major,
                os,
            );

            assert_eq!(result, expected, "case '{}' failed", name);
        }
    }
}
