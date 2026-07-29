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

# Sparkle 公钥（写入 Info.plist 的 SUPublicEDKey），从环境变量读取，允许为空
SPARKLE_PUBLIC_KEY="${SPARKLE_PUBLIC_KEY:-}"

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
    <string>${SPARKLE_PUBLIC_KEY}</string>
</dict>
</plist>
PLIST

# 下载 Sparkle Framework（编译启动器前需要，canImport(Sparkle) 在编译期检查）
echo "下载 Sparkle Framework..."
SPARKLE_VERSION="2.6.4"
SPARKLE_URL="https://github.com/sparkle-project/Sparkle/releases/download/${SPARKLE_VERSION}/Sparkle-${SPARKLE_VERSION}.tar.xz"
curl -L "$SPARKLE_URL" -o /tmp/sparkle.tar.xz
mkdir -p /tmp/sparkle_extract
tar -xf /tmp/sparkle.tar.xz -C /tmp/sparkle_extract
cp -R /tmp/sparkle_extract/Sparkle.framework "$APP_DIR/Contents/Frameworks/"

# 正式发布时要求 Sparkle 必须编译成功（REQUIRE_SPARKLE=1），开发测试允许回退
REQUIRE_SPARKLE="${REQUIRE_SPARKLE:-0}"

# 5. 编译 Swift 启动器
echo "[5/7] 编译 Swift 启动器..."
LAUNCHER_DIR="$PROJECT_ROOT/packaging/macos/launcher"

# 先尝试带 Sparkle 编译，失败则不带 Sparkle 编译
if [ -d "$APP_DIR/Contents/Frameworks/Sparkle.framework" ]; then
    swiftc \
        "$LAUNCHER_DIR/main.swift" \
        "$LAUNCHER_DIR/Updater.swift" \
        -framework Cocoa \
        -F "$APP_DIR/Contents/Frameworks" \
        -framework Sparkle \
        -Xlinker -rpath \
        -Xlinker "@executable_path/../Frameworks" \
        -o "$APP_DIR/Contents/MacOS/StockHelperLauncher" 2>/dev/null || {
        if [ "$REQUIRE_SPARKLE" = "1" ]; then
            echo "错误: Sparkle 编译失败，正式发布不允许跳过"
            exit 1
        fi
        echo "Sparkle 编译失败，回退到不带 Sparkle 的版本..."
        swiftc \
            "$LAUNCHER_DIR/main.swift" \
            -framework Cocoa \
            -o "$APP_DIR/Contents/MacOS/StockHelperLauncher"
    }
else
    swiftc \
        "$LAUNCHER_DIR/main.swift" \
        -framework Cocoa \
        -o "$APP_DIR/Contents/MacOS/StockHelperLauncher"
fi

if [ ! -f "$APP_DIR/Contents/MacOS/StockHelperLauncher" ]; then
    echo "错误: Swift 启动器编译失败"
    exit 1
fi
echo "Swift 启动器编译成功"

# 6a. Developer ID 签名（如果证书存在）
DEVELOPER_ID="${MACOS_CERTIFICATE_NAME:-}"
NOTARY_APPLE_ID="${APPLE_ID:-}"
NOTARY_TEAM_ID="${APPLE_TEAM_ID:-}"
NOTARY_PASSWORD="${APPLE_APP_PASSWORD:-}"

# 正式模式下强制签名
if [ "$REQUIRE_SPARKLE" = "1" ]; then
    if [ -z "$DEVELOPER_ID" ]; then
        echo "错误: 正式发布要求 Developer ID 证书名称"
        exit 1
    fi
    if [ -z "$NOTARY_APPLE_ID" ] || [ -z "$NOTARY_TEAM_ID" ] || [ -z "$NOTARY_PASSWORD" ]; then
        echo "错误: 正式发布要求 Apple 公证凭据"
        exit 1
    fi
fi

if [ -n "$DEVELOPER_ID" ]; then
    echo "  对 Sparkle Framework 签名..."
    codesign --force --deep --strict --sign "$DEVELOPER_ID" \
        --options runtime --timestamp \
        "$APP_DIR/Contents/Frameworks/Sparkle.framework"

    echo "  对后端二进制签名..."
    codesign --force --sign "$DEVELOPER_ID" \
        --options runtime --timestamp \
        "$APP_DIR/Contents/Resources/backend/stock-helper-server"

    echo "  对 Swift 启动器签名..."
    codesign --force --sign "$DEVELOPER_ID" \
        --options runtime --timestamp \
        "$APP_DIR/Contents/MacOS/StockHelperLauncher"

    echo "  对整个 .app 签名..."
    codesign --force --deep --strict --sign "$DEVELOPER_ID" \
        --options runtime --timestamp \
        "$APP_DIR"

    echo "  验证签名..."
    codesign --verify --deep --strict --verbose=2 "$APP_DIR"
    echo "  签名验证通过"
fi

# 6b. Apple 公证（如果凭据存在）
if [ -n "$NOTARY_APPLE_ID" ] && [ -n "$NOTARY_TEAM_ID" ] && [ -n "$NOTARY_PASSWORD" ]; then
    echo "  生成公证用 ZIP..."
    NOTARY_ZIP="$DIST_DIR/notary_temp.zip"
    ditto -c -k --keepParent "$APP_DIR" "$NOTARY_ZIP"

    echo "  提交 Apple 公证..."
    xcrun notarytool submit "$NOTARY_ZIP" \
        --apple-id "$NOTARY_APPLE_ID" \
        --team-id "$NOTARY_TEAM_ID" \
        --password "$NOTARY_PASSWORD" \
        --wait

    echo "  写入公证票据..."
    xcrun stapler staple "$APP_DIR"

    echo "  验证公证..."
    spctl --assess --type execute --verbose "$APP_DIR"
    echo "  公证验证通过"

    rm -f "$NOTARY_ZIP"
fi

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
