#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import os
import re
import subprocess
import sys
from pathlib import Path


def run_sign_update(tool: Path, dmg: Path, private_key: str) -> tuple[str, str]:
    completed = subprocess.run(
        [str(tool), str(dmg)],
        input=private_key + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(output.strip() or "sign_update failed")

    signature_match = re.search(r'sparkle:edSignature="([^"]+)"', output)
    length_match = re.search(r'(?:sparkle:)?length="([0-9]+)"', output)
    if not signature_match or not length_match:
        raise RuntimeError(f"Could not parse sign_update output:\n{output}")

    return signature_match.group(1), length_match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a single-item Sparkle appcast.")
    parser.add_argument("--dmg", required=True, type=Path)
    parser.add_argument("--sign-update-tool", required=True, type=Path)
    parser.add_argument("--private-key-env", default="SPARKLE_PRIVATE_ED_KEY")
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--release-notes-url", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--build-version", required=True)
    parser.add_argument("--minimum-system-version", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--channel")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    private_key = os.environ.get(args.private_key_env, "").strip()
    if not private_key:
        raise RuntimeError(f"{args.private_key_env} is not configured")

    if not args.dmg.is_file():
        raise RuntimeError(f"DMG not found: {args.dmg}")

    signature, length = run_sign_update(args.sign_update_tool, args.dmg, private_key)
    pub_date = dt.datetime.now(dt.UTC).strftime("%a, %d %b %Y %H:%M:%S %z")

    channel = ""
    if args.channel:
        channel = f"        <sparkle:channel>{html.escape(args.channel)}</sparkle:channel>\n"

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>{html.escape(args.title)} Updates</title>
    <item>
      <title>{html.escape(args.title)}</title>
      <sparkle:version>{html.escape(args.build_version)}</sparkle:version>
      <sparkle:shortVersionString>{html.escape(args.version)}</sparkle:shortVersionString>
{channel}      <sparkle:minimumSystemVersion>{html.escape(args.minimum_system_version)}</sparkle:minimumSystemVersion>
      <sparkle:releaseNotesLink>{html.escape(args.release_notes_url)}</sparkle:releaseNotesLink>
      <pubDate>{pub_date}</pubDate>
      <enclosure url="{html.escape(args.download_url)}"
                 sparkle:edSignature="{html.escape(signature)}"
                 length="{html.escape(length)}"
                 type="application/octet-stream" />
    </item>
  </channel>
</rss>
"""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(xml, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
