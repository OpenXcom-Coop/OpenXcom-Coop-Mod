#!/usr/bin/env bash
set -euo pipefail

app="${1:?usage: bundle_macos_sdl_runtime.sh /path/to/openxcom.app}"
frameworks="$app/Contents/Frameworks"
mkdir -p "$frameworks"

copy_runtime() {
  local formula="$1"
  local filename="$2"
  local source="$(brew --prefix "$formula")/lib/$filename"
  local destination="$frameworks/$filename"

  if [[ ! -e "$source" ]]; then
    echo "::error::$formula did not provide $source"
    find "$(brew --prefix "$formula")/lib" -maxdepth 1 -name '*.dylib' -print || true
    exit 1
  fi

  # Dereference Homebrew's versioned symlink so the app contains the actual
  # library under the exact filename used by the compatibility layer's dlopen().
  cp -L "$source" "$destination"
  chmod u+w "$destination"
  install_name_tool -id "@rpath/$filename" "$destination"

  # Homebrew adds runtime search paths that only exist on the build runner.
  # The bundled compatibility libraries find each other through @loader_path,
  # so these external paths are not needed in the distributed application.
  while IFS= read -r rpath; do
    case "$rpath" in
      /opt/homebrew/*|/usr/local/*|/Users/runner/work/*)
        install_name_tool -delete_rpath "$rpath" "$destination"
        ;;
    esac
  done < <(otool -l "$destination" | awk '/cmd LC_RPATH/ { getline; getline; print $2 }')

  file "$destination"
  file "$destination" | grep -q 'arm64'
}

# sdl12-compat loads this exact SDL2 filename at runtime. Homebrew's SDL2
# implementation is sdl2-compat, which then loads libSDL3.dylib at runtime.
copy_runtime sdl2-compat libSDL2-2.0.0.dylib
copy_runtime sdl3 libSDL3.dylib

# Also provide the alternate SDL2 filename that sdl12-compat checks on macOS.
ln -sfn libSDL2-2.0.0.dylib "$frameworks/libSDL2-2.0.dylib"

printf '%s\n' 'Bundled SDL runtime libraries:'
ls -l "$frameworks"/libSDL2*.dylib "$frameworks"/libSDL3*.dylib
