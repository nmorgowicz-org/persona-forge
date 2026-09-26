#!/usr/bin/env python3
"""Write a one-item Sparkle 2 `appcast.xml` (spike 1A task 2; contract §9.1 shape).

usage: make_appcast.py --version V --url DMG_URL --length BYTES --signature ED_SIG_B64 --out PATH

`--signature` is the base64 EdDSA signature of the DMG (the `spike-sparkle-sig` output) and
`--length` its byte size; Sparkle rejects the update if either does not match the download.
`sparkle:version` is compared with the installed app's CFBundleVersion, which Tauri sets to the
build version.
"""
import argparse
import email.utils
import sys
import xml.etree.ElementTree as ET

SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--length", required=True, type=int)
    ap.add_argument("--signature", required=True)
    ap.add_argument("--minimum-system-version", default="14.0")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.length <= 0:
        sys.exit("--length must be positive")
    if not args.signature.strip():
        sys.exit("--signature is empty")

    ET.register_namespace("sparkle", SPARKLE_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "desktop-spike"
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = args.version
    ET.SubElement(item, "pubDate").text = email.utils.formatdate(usegmt=True)
    ET.SubElement(item, f"{{{SPARKLE_NS}}}version").text = args.version
    ET.SubElement(item, f"{{{SPARKLE_NS}}}shortVersionString").text = args.version
    ET.SubElement(item, f"{{{SPARKLE_NS}}}minimumSystemVersion").text = args.minimum_system_version
    ET.SubElement(item, "enclosure", {
        "url": args.url,
        "length": str(args.length),
        "type": "application/octet-stream",
        f"{{{SPARKLE_NS}}}edSignature": args.signature.strip(),
    })
    tree = ET.ElementTree(rss)
    ET.indent(tree)
    try:
        tree.write(args.out, encoding="utf-8", xml_declaration=True)
    except OSError as exc:
        sys.exit(f"cannot write {args.out}: {exc}")
    print(f"wrote {args.out}: {args.version} -> {args.url} ({args.length} bytes)")


if __name__ == "__main__":
    main()
