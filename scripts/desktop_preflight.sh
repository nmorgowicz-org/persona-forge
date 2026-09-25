#!/usr/bin/env bash
# Desktop toolchain preflight (execution plan Phase 0, task 2).
#
# Usage: desktop_preflight.sh <macos|windows|linux>
#
# Checks every tool the desktop build/sign/smoke lanes need for one runner OS.
# Each check prints the tool's version, or exactly one `MISSING: <tool>` line.
# Exits 1 at the END if anything was missing, so one run yields the complete
# list (that list becomes the owner's install task, OA-6 / Phase 0R image work).
#
# Runs in Git Bash on Windows (self-hosted-windows has bash via Git for Windows).

set -u

OS_ARG="${1:-}"

failures=0

ok() { # ok <tool> <version-output>
  printf 'OK      %s: %s\n' "$1" "$2"
}

missing() { # missing <tool> [detail]
  printf 'MISSING %s%s\n' "$1" "${2:+ ($2)}"
  failures=$((failures + 1))
}

# ok/missing wrapper for a plain command lookup + version print.
# check_tool <tool> <version-cmd...>
check_tool() {
  local tool="$1"
  shift
  local out
  if out=$("$@" 2>&1); then
    ok "$tool" "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-120)"
  else
    missing "$tool"
  fi
}

case "$OS_ARG" in
  macos|windows|linux) ;;
  *)
    echo "usage: $0 <macos|windows|linux>" >&2
    exit 2
    ;;
esac

echo "== desktop preflight: $OS_ARG =="

# --- all OSes ---------------------------------------------------------------

check_tool "rustc" rustc --version
check_tool "cargo" cargo --version

if rustup target list --installed >/dev/null 2>&1; then
  ok "rustup-targets" "$(rustup target list --installed | tr '\n' ' ')"
else
  missing "rustup-targets" "rustup target list --installed failed"
fi

check_tool "python3" python3 --version

# uv: warn only (it is fetched pinned per-job by fetch_uv_binary.sh, not
# required on the runner's PATH).
if command -v uv >/dev/null 2>&1; then
  ok "uv" "$(uv --version 2>&1)"
else
  echo "WARN    uv: not on PATH (warn-only; jobs fetch a pinned uv)"
fi

# --- macOS ------------------------------------------------------------------

if [ "$OS_ARG" = "macos" ]; then
  if xcode_select_path=$(xcode-select -p 2>&1); then
    ok "xcode-select" "$xcode_select_path"
  else
    missing "xcode-select" "no developer directory (install Xcode Command Line Tools)"
  fi

  for tool in hdiutil codesign spctl; do
    if command -v "$tool" >/dev/null 2>&1; then
      ok "$tool" "$(command -v "$tool")"
    else
      missing "$tool"
    fi
  done

  if xcrun stapler help >/dev/null 2>&1 || xcrun stapler 2>&1 | grep -qi stapler; then
    ok "xcrun-stapler" "$(xcrun stapler 2>&1 | grep -i 'stapler' | cut -c1-100)"
  else
    missing "xcrun-stapler" "xcrun stapler not available"
  fi

  # >= 10 GB free on $RUNNER_TEMP (Tauri target dirs are large).
  scan_dir="${RUNNER_TEMP:-$HOME}"
  free_gb=$(df -g "$scan_dir" 2>/dev/null | awk 'NR==2 {print $4}')
  if [ -n "${free_gb:-}" ] && [ "$free_gb" -ge 10 ] 2>/dev/null; then
    ok "free-disk" "${free_gb} GB free on $scan_dir (>= 10 GB)"
  else
    missing "free-disk" "${free_gb:-unknown} GB free on $scan_dir, need >= 10"
  fi
fi

# --- Windows (Git Bash) -----------------------------------------------------

if [ "$OS_ARG" = "windows" ]; then
  # MSVC C++ tools reachable through vswhere.
  VSWHERE="/c/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe"
  if [ -x "$VSWHERE" ]; then
    vs_path=$("$VSWHERE" -latest -products '*' \
      -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 \
      -property installationPath 2>/dev/null)
    if [ -n "$vs_path" ]; then
      ok "vswhere-vc-tools" "$vs_path"
    else
      missing "vswhere-vc-tools" "no install with VC.Tools.x86.x64 (VS 2022 Build Tools)"
    fi
  else
    missing "vswhere-vc-tools" "vswhere.exe not found"
  fi

  # Windows SDK.
  sdk_found=""
  for sdk_dir in "/c/Program Files (x86)/Windows Kits/10/Include"/*; do
    [ -d "$sdk_dir" ] && sdk_found="$sdk_dir" && break
  done
  if [ -n "$sdk_found" ]; then
    ok "windows-sdk" "$sdk_found"
  else
    missing "windows-sdk" "no SDK under C:/Program Files (x86)/Windows Kits/10/Include"
  fi

  # WebView2 Evergreen runtime (HKLM machine-wide, or HKCU per-user).
  webview2_key='{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
  if reg.exe query "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\${webview2_key}" >/dev/null 2>&1 \
    || reg.exe query "HKCU\\Software\\Microsoft\\EdgeUpdate\\Clients\\${webview2_key}" >/dev/null 2>&1; then
    ok "webview2-runtime" "pv registry entry found"
  else
    missing "webview2-runtime" "no EdgeUpdate Clients registry entry (HKLM WOW6432Node or HKCU)"
  fi
fi

# --- Linux ------------------------------------------------------------------

if [ "$OS_ARG" = "linux" ]; then
  # The runner image's glibc sets the oldest distro the AppImage supports;
  # it must be <= 2.35 (Ubuntu 22.04 baseline, contract D8).
  read -r _ _ ldd_version _ < <(ldd --version 2>/dev/null)
  if [ -n "${ldd_version:-}" ]; then
    if printf '%s\n' "2.35" "$ldd_version" | sort -V | tail -1 | grep -q "^${ldd_version}$"; then
      ok "glibc" "$ldd_version (<= 2.35)"
    else
      missing "glibc" "$ldd_version > 2.35; AppImage would not run on Ubuntu 22.04"
    fi
  else
    missing "glibc" "ldd --version produced nothing"
  fi

  for pkg in webkit2gtk-4.1 gtk+-3.0 ayatana-appindicator3-0.1 gstreamer-1.0; do
    if pkg_version=$(pkg-config --modversion "$pkg" 2>/dev/null); then
      ok "pkg-config:$pkg" "$pkg_version"
    else
      missing "pkg-config:$pkg"
    fi
  done

  for tool in patchelf xvfb-run WebKitWebDriver tauri-driver; do
    if command -v "$tool" >/dev/null 2>&1; then
      ok "$tool" "$(command -v "$tool")"
    else
      missing "$tool"
    fi
  done

  check_tool "rcodesign" rcodesign --version

  # OpenSSL 3 (Ed25519 -rawin for the Sparkle feed signature); LibreSSL rejected.
  if openssl_version=$(openssl version 2>/dev/null); then
    case "$openssl_version" in
      "OpenSSL 3"*) ok "openssl" "$openssl_version" ;;
      *) missing "openssl" "$openssl_version; need OpenSSL 3 (Ed25519 -rawin)" ;;
    esac
  else
    missing "openssl" "openssl not found"
  fi
fi

echo "== preflight done: $failures missing =="

if [ "$failures" -gt 0 ]; then
  exit 1
fi
exit 0
