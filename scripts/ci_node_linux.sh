#!/usr/bin/env bash
# Prove the Node toolchain on Linux runners, and provision it when actions/setup-node lied.
#
# actions/setup-node downgrades a failed manifest/download/extract to `core.info` and still
# adds a path, so the step can report success while no `node` is on PATH
# (https://github.com/actions/setup-node/issues/1556). Its own retries all hit the same GitHub
# manifest host, so a pod with stalled egress spends them and still reaches the next step
# without a toolchain. This gate names the requirement (default Node ^24.11.0, the floor
# Renovate 44 declares) and, when the action installed nothing, fetches the official tarball
# from nodejs.org with the bounded-retry shape the other network steps in CI use.
#
# Usage: ci_node_linux.sh [major] [min_minor] [attempts]
set -euo pipefail

major=${1:-24}
min_minor=${2:-11}
attempts=${3:-5}

if [[ "$(uname -s)" != Linux ]]; then
  echo "ci_node_linux: not Linux, nothing to verify"
  exit 0
fi

require() {
  command -v node >/dev/null 2>&1 || return 1
  command -v npm >/dev/null 2>&1 || return 1
  command -v npx >/dev/null 2>&1 || return 1
  node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major === +process.argv[1] && minor >= +process.argv[2] ? 0 : 1)' "$major" "$min_minor"
}

report() {
  command -v node npm npx
  echo "node $(node --version), npm $(npm --version), npx $(npx --version)"
  echo "PATH=$PATH"
  echo "RUNNER_TOOL_CACHE=${RUNNER_TOOL_CACHE:-unset}"
}

if require; then
  report
  exit 0
fi

echo "::warning::no usable Node ${major}.${min_minor} on PATH; setup-node did not install one, provisioning from nodejs.org"

case "$(uname -m)" in
  x86_64 | amd64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *)
    echo "::error::unsupported architecture $(uname -m)"
    exit 1
    ;;
esac

# Idleness-bounded, not transfer-bounded: a stalled read is abandoned and retried, a slow but
# flowing download is untouched.
fetch() {
  curl -fsSL --connect-timeout 10 --max-time 300 --retry 2 --retry-all-errors --retry-delay 2 "$@"
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

dist="https://nodejs.org/dist/latest-v${major}.x"
for attempt in $(seq 1 "$attempts"); do
  work=$(mktemp -d)
  if fetch -o "$work/SHASUMS256.txt" "$dist/SHASUMS256.txt"; then
    # The checksum list names the published archives; it is the only index this script needs.
    archive=$(awk -v want="linux-${arch}.tar.gz" '$2 ~ ("-" want "$") { print $2; exit }' "$work/SHASUMS256.txt")
    expected=$(awk -v name="$archive" '$2 == name { print $1 }' "$work/SHASUMS256.txt")
    if [[ -n "$archive" && -n "$expected" ]] && fetch -o "$work/$archive" "$dist/$archive"; then
      actual=$(sha256_of "$work/$archive")
      if [[ "$actual" == "$expected" ]]; then
        tar -xzf "$work/$archive" -C "$work"
        installed="$work/${archive%.tar.gz}"
        if [[ -x "$installed/bin/node" ]]; then
          if [[ -n "${GITHUB_PATH:-}" ]]; then
            echo "$installed/bin" >>"$GITHUB_PATH"
          fi
          PATH="$installed/bin:$PATH"
          export PATH
          if require; then
            echo "::warning::provisioned Node from nodejs.org after attempt ${attempt}/${attempts}"
            report
            exit 0
          fi
        fi
        echo "::warning::extracted $archive but it holds no usable node (attempt ${attempt}/${attempts})"
      else
        echo "::warning::sha256 mismatch for $archive (attempt ${attempt}/${attempts})"
      fi
    fi
  fi
  echo "::warning::Node download attempt ${attempt}/${attempts} failed"
  rm -rf "$work"
  sleep $((attempt * 5))
done

echo "::error::no Node ${major}.${min_minor} toolchain after ${attempts} attempts; setup-node reported success without installing one and nodejs.org did not deliver"
exit 1
