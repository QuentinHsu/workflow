#!/usr/bin/env bash
set -euo pipefail

tag="${1:?tag is required}"
version="${2:?version is required}"
output="${3:?output path is required}"
changelog="${CHANGELOG_PATH:-CHANGELOG.md}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$changelog" ]]; then
  if python3 - "$changelog" "$version" "$output" <<'PY'
import pathlib
import re
import sys

changelog = pathlib.Path(sys.argv[1])
version = sys.argv[2]
output = pathlib.Path(sys.argv[3])

content = changelog.read_text(encoding="utf-8")
pattern = re.compile(rf"^##\s+v?{re.escape(version)}\s*$\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
match = pattern.search(content)
if match:
    body = match.group(1).strip()
    if body:
        output.write_text(body + "\n", encoding="utf-8")
        raise SystemExit(0)

raise SystemExit(1)
PY
  then
    exit 0
  fi
fi

previous_tag="$(
  git tag -l 'v[0-9]*.[0-9]*.[0-9]*' '[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname |
    grep -Fxv "$tag" |
    head -n 1 || true
)"

range="$tag"
if [[ -n "$previous_tag" ]]; then
  range="${previous_tag}..${tag}"
fi

if [[ -f "${script_dir}/update_changelog.py" ]]; then
  if python3 "${script_dir}/update_changelog.py" \
    --version "$version" \
    --from-ref "$previous_tag" \
    --to-ref "$tag" \
    --changelog "$changelog" \
    --project-name "${APP_DISPLAY_NAME:-}" \
    --language "${CHANGELOG_LANGUAGE:-zh-CN}" \
    --mode body >"$output"; then
    exit 0
  fi
fi

{
  if [[ -n "${APP_DISPLAY_NAME:-}" ]]; then
    echo "## ${APP_DISPLAY_NAME} ${version}"
  else
    echo "## v${version}"
  fi
  echo
  if git log --format='- %s (%h)' "$range" | grep -q .; then
    git log --format='- %s (%h)' "$range"
  else
    echo "- Release ${version}"
  fi
} > "$output"
