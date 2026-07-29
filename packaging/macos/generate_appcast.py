#!/usr/bin/env python3
"""生成 Sparkle appcast.xml 更新清单"""
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime

def generate_appcast(app_path: str, version: str, output_path: str = "appcast.xml"):
    """生成 Sparkle appcast.xml"""
    # 确保版本号不含 v 前缀，避免 URL 中出现 vv
    version = version.lstrip('v')
    app = Path(app_path)
    if not app.exists():
        print(f"错误: 文件不存在 {app}")
        sys.exit(1)

    # 计算 SHA-256
    sha256 = hashlib.sha256(app.read_bytes()).hexdigest()
    size = app.stat().st_size
    pub_date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    xml = f"""<?xml version="1.0" standalone="yes"?>
<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle" version="2.0">
  <channel>
    <title>股票分析助手更新</title>
    <item>
      <title>版本 {version}</title>
      <pubDate>{pub_date}</pubDate>
      <sparkle:version>{version}</sparkle:version>
      <sparkle:shortVersionString>{version}</sparkle:shortVersionString>
      <sparkle:dsaSignature></sparkle:dsaSignature>
      <!-- 需要使用 Sparkle 的 sign_update 工具生成 EdDSA 签名后填入 sparkle:edSignature -->
      <enclosure
        url="https://github.com/devotionn/Stock-Helper/releases/download/v{version}/StockHelper-{version}.zip"
        sparkle:edSignature=""
        length="{size}"
        type="application/octet-stream"
      />
      <description>
        <![CDATA[
          <p>股票分析助手 {version} 更新</p>
          <p>不会删除您的文字、图片和历史记录。</p>
        ]]>
      </description>
    </item>
  </channel>
</rss>"""

    Path(output_path).write_text(xml, encoding="utf-8")
    print(f"appcast.xml 已生成: {output_path}")
    print(f"版本: {version}")
    print(f"大小: {size} bytes")
    print(f"SHA-256: {sha256}")
    print("请使用 Sparkle 的 sign_update 工具生成 EdDSA 签名:")
    print(f"  ./bin/sign_update {app_path} <private_key>")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python generate_appcast.py <app_zip_path> <version> [output_path]")
        sys.exit(1)
    generate_appcast(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "appcast.xml")
