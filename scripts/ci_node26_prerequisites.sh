#!/usr/bin/env bash
# Run before actions/setup-node for Node 26 on Debian/Ubuntu ARC runners.
# Official Linux binaries require libatomic at runtime starting with Node 25:
# https://raw.githubusercontent.com/nodejs/node/v26.12.1/BUILDING.md
# This provisions a required dependency; the earlier ARC exit 127 had no captured
# loader stderr, so it does not establish the cause of that historical failure.
set -euo pipefail

if [[ "$(uname -s)" != Linux ]]; then
  exit 0
fi

# Avoid apt/network/sudo entirely when the native runtime package is installed.
if [[ "$(dpkg-query -W -f='${Status}' libatomic1 2>/dev/null)" == 'install ok installed' ]]; then
  exit 0
fi

privilege=()
if [[ "$(id -u)" != 0 ]]; then
  privilege=(sudo -n)
fi

# Fail closed on either apt failure; never continue to setup-node without the dep.
"${privilege[@]}" env DEBIAN_FRONTEND=noninteractive apt-get update
"${privilege[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libatomic1
