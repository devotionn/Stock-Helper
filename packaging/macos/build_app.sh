#!/bin/bash
# 构建、签名并公证 macOS Apple Silicon 应用。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"
APP_VERSION="${VERSION:-1.0.0}"
APP_VERSION="${APP_VERSION#v}"
APP_DIR="$DIST_DIR/股票分析助手.app"
ENABLE_SPARKLE="${ENABLE_SPARKLE:-1}"
RELEASE_MODE="${RELEASE_MODE:-0}"
SPARKLE_VERSION="${SPARKLE_VERSION:-2.9.2}"
SPARKLE_PUBLIC_KEY="${SPARKLE_PUBLIC_KEY:-}"
SPARKLE_ARCHIVE_SHA256="${SPARKLE_ARCHIVE_SHA256:-}"
SPARKLE_TEMP="$(mktemp -d "${RUNNER_TEMP:-/tmp}/stock-helper-sparkle.XXXXXX")"

cleanup() {
  rm -rf "$SPARKLE_TEMP"
}
trap cleanup EXIT

if [[ ! "$APP_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "错误: VERSION 必须是 x.y.z 格式，当前值: $APP_VERSION"
  exit 1
fi

if [[ "$RELEASE_MODE" == "1" ]]; then
  ENABLE_SPARKLE=1
  for required_name in SPARKLE_PUBLIC_KEY SPARKLE_ARCHIVE_SHA256 MACOS_CERTIFICATE_NAME APPLE_ID APPLE_TEAM_ID APPLE_APP_PASSWORD; do
    if [[ -z "${!required_name:-}" ]]; then
      echo "错误: 正式发布缺少 $required_name"
      exit 1
    fi
  done
fi

echo "=== 股票分析助手 macOS 构建 v$APP_VERSION ==="
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

cd "$PROJECT_ROOT/frontend"
npm ci
npm run lint
npm run build

cd "$PROJECT_ROOT/backend"
pip install -r requirements.txt -r requirements-dev.txt
cd "$PROJECT_ROOT"
pyinstaller packaging/macos/stock-helper.spec \
  --noconfirm --clean --distpath "$DIST_DIR" --workpath "$BUILD_DIR"

mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$APP_DIR/Contents/Frameworks"
cp -R "$DIST_DIR/stock-helper-server" "$APP_DIR/Contents/Resources/backend"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>股票分析助手</string>
  <key>CFBundleDisplayName</key><string>股票分析助手</string>
  <key>CFBundleIdentifier</key><string>com.stockhelper.app</string>
  <key>CFBundleVersion</key><string>${APP_VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${APP_VERSION}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>StockHelperLauncher</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSAllowsLocalNetworking</key><true/>
    <key>NSExceptionDomains</key>
    <dict>
      <key>127.0.0.1</key>
      <dict><key>NSExceptionAllowsInsecureHTTPLoads</key><true/></dict>
      <key>localhost</key>
      <dict><key>NSExceptionAllowsInsecureHTTPLoads</key><true/></dict>
    </dict>
  </dict>
</dict>
</plist>
PLIST

if [[ "$ENABLE_SPARKLE" == "1" ]]; then
  [[ -n "$SPARKLE_PUBLIC_KEY" ]] || { echo "错误: 启用 Sparkle 时必须提供 SPARKLE_PUBLIC_KEY"; exit 1; }
  [[ -n "$SPARKLE_ARCHIVE_SHA256" ]] || { echo "错误: 启用 Sparkle 时必须提供 SPARKLE_ARCHIVE_SHA256"; exit 1; }

  SPARKLE_ARCHIVE="$SPARKLE_TEMP/Sparkle-${SPARKLE_VERSION}.tar.xz"
  SPARKLE_URL="https://github.com/sparkle-project/Sparkle/releases/download/${SPARKLE_VERSION}/Sparkle-${SPARKLE_VERSION}.tar.xz"
  curl --fail --location --retry 3 --retry-delay 2 "$SPARKLE_URL" -o "$SPARKLE_ARCHIVE"
  echo "${SPARKLE_ARCHIVE_SHA256}  ${SPARKLE_ARCHIVE}" | shasum -a 256 -c -
  tar -xf "$SPARKLE_ARCHIVE" -C "$SPARKLE_TEMP"
  SPARKLE_FRAMEWORK="$(find "$SPARKLE_TEMP" -maxdepth 3 -name Sparkle.framework -type d | head -1)"
  [[ -n "$SPARKLE_FRAMEWORK" ]] || { echo "错误: Sparkle.framework 未找到"; exit 1; }
  cp -R "$SPARKLE_FRAMEWORK" "$APP_DIR/Contents/Frameworks/"

  /usr/libexec/PlistBuddy -c "Add :SUFeedURL string https://github.com/devotionn/Stock-Helper/releases/latest/download/appcast.xml" "$APP_DIR/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Add :SUEnableAutomaticChecks bool true" "$APP_DIR/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Add :SUScheduledCheckInterval integer 86400" "$APP_DIR/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Add :SUPublicEDKey string $SPARKLE_PUBLIC_KEY" "$APP_DIR/Contents/Info.plist"

  mkdir -p "$DIST_DIR/sparkle-tools"
  SIGN_TOOL="$(find "$SPARKLE_TEMP" -name sign_update -type f | head -1)"
  [[ -n "$SIGN_TOOL" ]] || { echo "错误: sign_update 未找到"; exit 1; }
  cp "$SIGN_TOOL" "$DIST_DIR/sparkle-tools/sign_update"
  chmod +x "$DIST_DIR/sparkle-tools/sign_update"
fi

LAUNCHER_DIR="$PROJECT_ROOT/packaging/macos/launcher"
if [[ "$ENABLE_SPARKLE" == "1" ]]; then
  swiftc "$LAUNCHER_DIR/main.swift" "$LAUNCHER_DIR/Updater.swift" \
    -framework Cocoa \
    -F "$APP_DIR/Contents/Frameworks" -framework Sparkle \
    -Xlinker -rpath -Xlinker "@executable_path/../Frameworks" \
    -o "$APP_DIR/Contents/MacOS/StockHelperLauncher"
else
  swiftc "$LAUNCHER_DIR/main.swift" -framework Cocoa \
    -o "$APP_DIR/Contents/MacOS/StockHelperLauncher"
fi
chmod +x "$APP_DIR/Contents/MacOS/StockHelperLauncher"
plutil -lint "$APP_DIR/Contents/Info.plist"

DEVELOPER_ID="${MACOS_CERTIFICATE_NAME:-}"
if [[ -n "$DEVELOPER_ID" ]]; then
  if [[ "$ENABLE_SPARKLE" == "1" ]]; then
    SPARKLE_CURRENT="$APP_DIR/Contents/Frameworks/Sparkle.framework/Versions/Current"
    [[ -e "$SPARKLE_CURRENT" ]] || { echo "错误: Sparkle Versions/Current 不存在"; exit 1; }
    codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$SPARKLE_CURRENT/XPCServices/Installer.xpc"
    codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp --preserve-metadata=entitlements "$SPARKLE_CURRENT/XPCServices/Downloader.xpc"
    codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$SPARKLE_CURRENT/Autoupdate"
    codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$SPARKLE_CURRENT/Updater.app"
    codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$APP_DIR/Contents/Frameworks/Sparkle.framework"
  fi

  BACKEND_DIR="$APP_DIR/Contents/Resources/backend"
  while IFS= read -r -d '' binary; do
    if file "$binary" | grep -q 'Mach-O'; then
      codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$binary"
    fi
  done < <(find "$BACKEND_DIR" -type f -print0)

  codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$APP_DIR/Contents/MacOS/StockHelperLauncher"
  codesign --force --sign "$DEVELOPER_ID" --options runtime --timestamp "$APP_DIR"
  codesign --verify --deep --strict --verbose=2 "$APP_DIR"
elif [[ "$RELEASE_MODE" == "1" ]]; then
  echo "错误: 正式发布没有 Developer ID"
  exit 1
fi

if [[ "$RELEASE_MODE" == "1" ]]; then
  NOTARY_ZIP="$DIST_DIR/notary-${APP_VERSION}.zip"
  ditto -c -k --keepParent "$APP_DIR" "$NOTARY_ZIP"
  xcrun notarytool submit "$NOTARY_ZIP" \
    --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" --wait
  xcrun stapler staple "$APP_DIR"
  xcrun stapler validate "$APP_DIR"
  spctl --assess --type execute --verbose=2 "$APP_DIR"
  rm -f "$NOTARY_ZIP"
fi

cd "$DIST_DIR"
rm -f "StockHelper-${APP_VERSION}.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "StockHelper-${APP_VERSION}.zip"

echo "构建完成: $APP_DIR"
echo "分发包: $DIST_DIR/StockHelper-${APP_VERSION}.zip"
