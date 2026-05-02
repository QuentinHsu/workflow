#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="${APP_PROJECT_DIR:-$PWD}"

cd "$project_dir"

if [[ -z "${SPARKLE_FEED_URL:-}" && -n "${APP_REPOSITORY:-}" ]]; then
  if [[ -n "${TARGET_ARCH:-}" ]]; then
    SPARKLE_FEED_URL="https://github.com/${APP_REPOSITORY}/releases/latest/download/appcast-${TARGET_ARCH}.xml"
  else
    SPARKLE_FEED_URL="https://github.com/${APP_REPOSITORY}/releases/latest/download/appcast.xml"
  fi
  export SPARKLE_FEED_URL
fi

source "${script_dir}/common/macos_app.sh"

command="${1:-all}"

case "$command" in
  app)
    macos_app_create_bundle
    ;;
  dmg)
    macos_app_create_bundle >/dev/null
    macos_app_create_dmg
    ;;
  all)
    macos_app_create_bundle >/dev/null
    macos_app_create_dmg
    ;;
  *)
    echo "Usage: $0 [app|dmg|all]" >&2
    exit 2
    ;;
esac
