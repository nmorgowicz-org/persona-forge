#!/usr/bin/env python3
"""Convert a raw Ed25519 seed (32 bytes) into a PKCS#8 PEM file (contract §9.2).

Used by the spike workflow's Sparkle signing step. Key material never touches
argv -- both paths come from argv, contents from files/stdin.

usage: seed_to_pem.py <seed-file> <out-pem>
"""
import sys


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <seed-file> <out-pem>")
    try:
        with open(sys.argv[1], "rb") as f:
            seed = f.read()
    except OSError as exc:
        sys.exit(f"cannot read seed: {exc}")
    if len(seed) != 32:
        sys.exit(f"seed must be exactly 32 raw bytes, got {len(seed)}")
    hexder = "302e020100300506032b657004220420" + seed.hex()
    lines = [hexder[i : i + 64] for i in range(0, len(hexder), 64)]
    try:
        with open(sys.argv[2], "w") as f:
            f.write("-----BEGIN PRIVATE KEY-----\n")
            for line in lines:
                f.write(line + "\n")
            f.write("-----END PRIVATE KEY-----\n")
    except OSError as exc:
        sys.exit(f"cannot write pem: {exc}")


if __name__ == "__main__":
    main()
