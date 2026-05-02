#!/usr/bin/env bash
set -euo pipefail

tag="${1:?tag is required}"
version="${2:?version is required}"
output="${3:?output path is required}"

previous_tag="$(
  git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname |
    grep -Fxv "$tag" |
    head -n 1 || true
)"

range="$tag"
if [[ -n "$previous_tag" ]]; then
  range="${previous_tag}..${tag}"
fi

{
  echo "## Skills Hub ${version}"
  echo
  if git log --format='- %s (%h)' "$range" | grep -q .; then
    git log --format='- %s (%h)' "$range"
  else
    echo "- Release ${version}"
  fi
} > "$output"
