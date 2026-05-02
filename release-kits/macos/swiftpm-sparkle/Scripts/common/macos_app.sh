#!/usr/bin/env bash

macos_app_require() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 1
  fi
}

macos_app_plist_read() {
  local key="$1"
  local plist="${INFO_PLIST:-Info.plist}"
  if [[ -f "$plist" ]]; then
    /usr/libexec/PlistBuddy -c "Print :${key}" "$plist" 2>/dev/null || true
  fi
}

macos_app_plist_set() {
  local plist="$1"
  local key="$2"
  local type="$3"
  local value="$4"

  if /usr/libexec/PlistBuddy -c "Print :${key}" "$plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :${key} ${value}" "$plist"
  else
    /usr/libexec/PlistBuddy -c "Add :${key} ${type} ${value}" "$plist"
  fi
}

macos_app_swift_args() {
  local args=(-c release)
  local archs="${BUILD_ARCHS:-${TARGET_ARCH:-}}"
  for arch in $archs; do
    args+=(--arch "$arch")
  done
  printf '%s\n' "${args[@]}"
}

macos_app_configure_deployment_target() {
  if [[ -n "${APP_MIN_MACOS:-}" && -z "${MACOSX_DEPLOYMENT_TARGET:-}" ]]; then
    export MACOSX_DEPLOYMENT_TARGET="$APP_MIN_MACOS"
  fi
}

macos_app_swift_bin_path() {
  macos_app_configure_deployment_target

  local args=()
  while IFS= read -r arg; do
    args+=("$arg")
  done < <(macos_app_swift_args)

  swift build "${args[@]}" --show-bin-path
}

macos_app_build_binary() {
  macos_app_configure_deployment_target

  local args=()
  while IFS= read -r arg; do
    args+=("$arg")
  done < <(macos_app_swift_args)

  swift build "${args[@]}"
}

macos_app_copy_frameworks() {
  local bin_path="$1"
  local app_bundle="$2"
  local frameworks_dir="${app_bundle}/Contents/Frameworks"
  mkdir -p "$frameworks_dir"

  find "$bin_path" -maxdepth 1 -name "*.framework" -type d -print0 2>/dev/null |
    while IFS= read -r -d '' framework; do
      ditto "$framework" "${frameworks_dir}/$(basename "$framework")"
    done
}

macos_app_sign_bundle() {
  local app_bundle="$1"
  local identity="${CODE_SIGN_IDENTITY:--}"

  local sign_args=(--force --options runtime)
  if [[ "$identity" != "-" ]]; then
    sign_args+=(--timestamp)
  else
    echo "CODE_SIGN_IDENTITY is not set; ad-hoc signing ${app_bundle}."
  fi
  sign_args+=(--sign "$identity")
  if [[ -n "${CODE_SIGN_ENTITLEMENTS:-}" ]]; then
    sign_args+=(--entitlements "$CODE_SIGN_ENTITLEMENTS")
  fi

  find "${app_bundle}/Contents/Frameworks" -type f -perm -111 -print0 2>/dev/null |
    while IFS= read -r -d '' executable; do
      codesign "${sign_args[@]}" "$executable"
    done

  find "${app_bundle}/Contents/Frameworks" \
    \( -name "*.app" -o -name "*.framework" -o -name "*.xpc" \) \
    -type d -print0 2>/dev/null |
    sort -rz |
    while IFS= read -r -d '' bundle; do
      codesign "${sign_args[@]}" "$bundle"
    done

  codesign "${sign_args[@]}" "$app_bundle"
  codesign --verify --deep --strict --verbose=2 "$app_bundle"
}

macos_app_validate_executable() {
  local executable="$1"

  if [[ ! -x "$executable" ]]; then
    echo "App executable is not executable: ${executable}" >&2
    exit 1
  fi

  local actual_archs=""
  actual_archs="$(lipo -archs "$executable" 2>/dev/null || true)"
  if [[ -n "$actual_archs" ]]; then
    echo "Built executable architectures: ${actual_archs}"
  fi

  if [[ -n "${TARGET_ARCH:-}" && -n "$actual_archs" ]]; then
    case " ${actual_archs} " in
      *" ${TARGET_ARCH} "*) ;;
      *)
        echo "Built executable does not contain requested architecture ${TARGET_ARCH}: ${actual_archs}" >&2
        exit 1
        ;;
    esac
  fi

  if command -v vtool >/dev/null 2>&1; then
    vtool -show-build "$executable" 2>/dev/null || true
  fi
}

macos_app_create_bundle() {
  macos_app_require APP_TARGET_NAME
  macos_app_require APP_DISPLAY_NAME
  macos_app_require APP_BUNDLE_ID

  local build_dir="${BUILD_DIR:-.build}"
  local app_bundle="${APP_BUNDLE_PATH:-${build_dir}/${APP_DISPLAY_NAME}.app}"
  local info_plist="${INFO_PLIST:-Info.plist}"
  local version="${APP_VERSION:-$(macos_app_plist_read CFBundleShortVersionString)}"
  local build_number="${BUILD_NUMBER:-$(macos_app_plist_read CFBundleVersion)}"
  local min_macos="${APP_MIN_MACOS:-$(macos_app_plist_read LSMinimumSystemVersion)}"

  version="${version:-1.0.0}"
  build_number="${build_number:-$version}"
  min_macos="${min_macos:-15.0}"

  macos_app_build_binary

  local bin_path
  bin_path="$(macos_app_swift_bin_path)"
  local executable="${bin_path}/${APP_TARGET_NAME}"
  if [[ ! -x "$executable" ]]; then
    echo "Built executable not found: ${executable}" >&2
    exit 1
  fi

  rm -rf "$app_bundle"
  mkdir -p "${app_bundle}/Contents/MacOS" "${app_bundle}/Contents/Resources"
  cp "$executable" "${app_bundle}/Contents/MacOS/${APP_TARGET_NAME}"
  chmod 755 "${app_bundle}/Contents/MacOS/${APP_TARGET_NAME}"
  cp "$info_plist" "${app_bundle}/Contents/Info.plist"

  local resource_bundle="${bin_path}/${APP_TARGET_NAME}_${APP_TARGET_NAME}.bundle"
  if [[ -d "$resource_bundle" ]]; then
    ditto "$resource_bundle" "${app_bundle}/Contents/Resources/$(basename "$resource_bundle")"
  fi

  if [[ -n "${APP_ICON_PATH:-}" && -f "$APP_ICON_PATH" ]]; then
    cp "$APP_ICON_PATH" "${app_bundle}/Contents/Resources/"
  fi

  macos_app_copy_frameworks "$bin_path" "$app_bundle"

  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundleName string "$APP_TARGET_NAME"
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundleDisplayName string "$APP_DISPLAY_NAME"
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundleIdentifier string "$APP_BUNDLE_ID"
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundleExecutable string "$APP_TARGET_NAME"
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundlePackageType string APPL
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundleShortVersionString string "$version"
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" CFBundleVersion string "$build_number"
  macos_app_plist_set "${app_bundle}/Contents/Info.plist" LSMinimumSystemVersion string "$min_macos"

  if [[ -n "${SPARKLE_FEED_URL:-}" ]]; then
    macos_app_plist_set "${app_bundle}/Contents/Info.plist" SUFeedURL string "$SPARKLE_FEED_URL"
  fi

  if [[ -n "${SPARKLE_PUBLIC_ED_KEY:-}" ]]; then
    macos_app_plist_set "${app_bundle}/Contents/Info.plist" SUPublicEDKey string "$SPARKLE_PUBLIC_ED_KEY"
  fi

  macos_app_sign_bundle "$app_bundle"
  macos_app_validate_executable "${app_bundle}/Contents/MacOS/${APP_TARGET_NAME}"

  echo "$app_bundle"
}

macos_app_create_dmg() {
  macos_app_require APP_TARGET_NAME

  local build_dir="${BUILD_DIR:-.build}"
  local dist_dir="${DIST_DIR:-dist}"
  local app_bundle="${APP_BUNDLE_PATH:-${build_dir}/${APP_DISPLAY_NAME}.app}"
  local version="${APP_VERSION:-$(macos_app_plist_read CFBundleShortVersionString)}"
  version="${version:-1.0.0}"

  if [[ ! -d "$app_bundle" ]]; then
    macos_app_create_bundle >/dev/null
  fi

  mkdir -p "$dist_dir"

  local arch_suffix=""
  if [[ -n "${TARGET_ARCH:-}" ]]; then
    arch_suffix="-${TARGET_ARCH}"
  fi
  local dmg_name="${DMG_NAME:-${APP_TARGET_NAME}-${version}${arch_suffix}.dmg}"
  local dmg_path="${dist_dir}/${dmg_name}"
  local staging="${build_dir}/dmg-root"

  rm -rf "$staging" "$dmg_path"
  mkdir -p "$staging"
  ditto "$app_bundle" "${staging}/$(basename "$app_bundle")"
  ln -s /Applications "${staging}/Applications"

  hdiutil create \
    -volname "$APP_DISPLAY_NAME" \
    -fs APFS \
    -format UDZO \
    -imagekey zlib-level=9 \
    -srcfolder "$staging" \
    -ov \
    -quiet \
    "$dmg_path"

  shasum -a 256 "$dmg_path" > "${dmg_path}.sha256"
  rm -rf "$staging"

  echo "$dmg_path"
}
