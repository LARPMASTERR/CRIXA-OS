#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

fail=0

check_required_files() {
  local src rel
  for src in "$PROJECT_ROOT/build/build.sh" "$PROJECT_ROOT/build/sync-rootfs.sh"; do
    while IFS= read -r rel; do
      [[ -z "$rel" ]] && continue
      if [[ ! -e "$PROJECT_ROOT/$rel" ]]; then
        echo "MISSING_REQUIRED:$rel (from $(basename "$src"))"
        fail=1
      fi
    done < <(grep -oP 'require_file "\$PROJECT_ROOT/\K[^"]+' "$src" || true)
  done
}

check_shell_syntax() {
  local s
  for s in "$PROJECT_ROOT"/build/*.sh "$PROJECT_ROOT"/apps/*.sh; do
    if ! bash -n "$s"; then
      echo "SHELL_SYNTAX_FAIL:${s#$PROJECT_ROOT/}"
      fail=1
    fi
  done
}

check_python_compile() {
  local p
  while IFS= read -r -d '' p; do
    if ! python3 -m py_compile "$p"; then
      echo "PY_COMPILE_FAIL:${p#$PROJECT_ROOT/}"
      fail=1
    fi
  done < <(find "$PROJECT_ROOT/apps" "$PROJECT_ROOT/store-backends" -type f -name '*.py' -print0)
}

check_desktop_icons() {
  local d icon
  while IFS= read -r -d '' d; do
    icon="$(grep -oP '^Icon=\K.+' "$d" || true)"
    if [[ -z "$icon" ]]; then
      continue
    fi
    if [[ "$icon" == crixa-* && ! -f "$PROJECT_ROOT/assets/icons/$icon.svg" ]]; then
      echo "ICON_MISSING:${d#$PROJECT_ROOT/} -> $icon"
      fail=1
    fi
  done < <(find "$PROJECT_ROOT/apps" -maxdepth 1 -type f -name '*.desktop' -print0)
}

main() {
  check_required_files
  check_shell_syntax
  check_python_compile
  check_desktop_icons

  if [[ "$fail" -eq 0 ]]; then
    echo "INTEGRITY_SCAN_OK"
    return 0
  fi

  echo "INTEGRITY_SCAN_FAIL"
  return 1
}

main "$@"
