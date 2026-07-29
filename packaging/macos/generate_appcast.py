#!/usr/bin/env python3
"""生成单版本 Sparkle appcast；签名由 Sparkle sign_update 产生。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr


def build_appcast(archive: Path, version: str, signature: str) -> str:
    if not archive.is_file():
        raise FileNotFoundError(archive)
    if not signature:
        raise ValueError("EdDSA signature 不能为空")
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("version 必须是 x.y.z")

    size = archive.stat().st_size
    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    download_url = (
        "https://github.com/devotionn/Stock-Helper/releases/download/"
        f"v{version}/StockHelper-{version}.zip"
    )
    return f'''<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle" version="2.0">
  <channel>
    <title>股票分析助手更新</title>
    <link>https://github.com/devotionn/Stock-Helper/releases</link>
    <description>股票分析助手正式更新</description>
    <language>zh-CN</language>
    <item>
      <title>版本 {escape(version)}</title>
      <pubDate>{pub_date}</pubDate>
      <sparkle:version>{escape(version)}</sparkle:version>
      <sparkle:shortVersionString>{escape(version)}</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>12.0</sparkle:minimumSystemVersion>
      <description><![CDATA[
        <p>股票分析助手 {escape(version)} 更新。</p>
        <p>安装更新前会自动备份数据库和图片，不会覆盖个人资料。</p>
      ]]></description>
      <enclosure url={quoteattr(download_url)}
        sparkle:edSignature={quoteattr(signature)}
        length={quoteattr(str(size))}
        type="application/octet-stream" />
    </item>
  </channel>
</rss>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("version")
    parser.add_argument("signature")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    xml = build_appcast(args.archive, args.version.lstrip("v"), args.signature)
    args.output.write_text(xml, encoding="utf-8")
    print(f"appcast 已生成: {args.output}")


if __name__ == "__main__":
    main()
