#!/bin/bash
# 构建 macOS .app
# 在 GitHub Actions macOS runner 或本地 M 系列 Mac 上执行
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== 股票分析助手 macOS 构建 ==="

# 版本号：优先使用环境变量 VERSION（由 CI 从 tag 传入），否则默认 1.0.0
APP_VERSION="${VERSION:-1.0.0}"
# 去掉可能的 v 前缀
APP_VERSION="${APP_VERSION#v}"
echo "版本号: $APP_VERSION"

# 1. 构建前端
echo "[1/7] 构建前端..."
cd "$PROJECT_ROOT/frontend"
npm ci
npm run build

# 2. 安装后端依赖
echo "[2/7] 安装后端依赖..."
cd "$PROJECT_ROOT/backend"
pip install -r requirements.txt -r requirements-dev.txt

# 3. PyInstaller 打包后端
echo "[3/7] PyInstaller 打包..."
cd "$PROJECT_ROOT"
pyinstaller packaging/macos/stock-helper.spec --noconfirm --distpath "$DIST_DIR" --workpath "$BUILD_DIR"

# 4. 组装 .app
echo "[4/7] 组装 .app..."
APP_DIR="$DIST_DIR/股票分析助手.app"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
mkdir -p "$APP_DIR/Contents/Frameworks"

# 复制后端
cp -r "$DIST_DIR/stock-helper-server" "$APP_DIR/Contents/Resources/backend"

# 创建 Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>股票分析助手</string>
    <key>CFBundleDisplayName</key>
    <string>股票分析助手</string>
    <key>CFBundleIdentifier</key>
    <string>com.stockhelper.app</string>
    <key>CFBundleVersion</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>StockHelperLauncher</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>SUFeedURL</key>
    <string>https://github.com/devotionn/Stock-Helper/releases/latest/download/appcast.xml</string>
    <key>SUEnableAutomaticChecks</key>
    <true/>
    <key>SUScheduledCheckInterval</key>
    <integer>86400</integer>
    <key>SUPublicEDKey</key>
    <string>待生成</string>
</dict>
</plist>
PLIST

# 创建启动脚本
cat > "$APP_DIR/Contents/MacOS/StockHelperLauncher" << LAUNCHER
#!/bin/bash
# 股票分析助手启动器
DIR="\$(dirname "\$(dirname "\$0")")/Resources/backend"
cd "\$DIR"
export PYTHONPATH="\$DIR"
exec "./stock-helper-server"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/StockHelperLauncher"

# 5. 下载 Sparkle Framework
echo "[5/7] 下载 Sparkle Framework..."
SPARKLE_VERSION="2.6.4"
SPARKLE_URL="https://github.com/sparkle-project/Sparkle/releases/download/${SPARKLE_VERSION}/Sparkle-${SPARKLE_VERSION}.tar.xz"
curl -L "$SPARKLE_URL" -o /tmp/sparkle.tar.xz
mkdir -p /tmp/sparkle_extract
tar -xf /tmp/sparkle.tar.xz -C /tmp/sparkle_extract
cp -R /tmp/sparkle_extract/Sparkle.framework "$APP_DIR/Contents/Frameworks/"

# 6. 创建分发包 zip
echo "[6/7] 创建分发包..."
cd "$DIST_DIR"
ditto -c -k --keepParent "$APP_DIR" "StockHelper-$APP_VERSION.zip"

# 7. 生成 appcast.xml
echo "[7/7] 生成 appcast.xml..."
python "$SCRIPT_DIR/generate_appcast.py" "$DIST_DIR/StockHelper-$APP_VERSION.zip" "$APP_VERSION" "$DIST_DIR/appcast.xml"

echo "构建完成: $APP_DIR"
echo ""
echo "下一步:"
echo "  1. codesign --deep --strict --sign 'Developer ID Application: YOUR_NAME' '$APP_DIR'"
echo "  2. xcrun notarytool submit 'StockHelper-$APP_VERSION.zip' --apple-id YOUR_ID --team-id TEAM_ID --wait"
echo "  3. xcrun stapler staple '$APP_DIR'"
