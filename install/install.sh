#!/bin/sh
set -eu

REPO="https://github.com/fstandhartinger/decisionmodels-local"
if [ -n "${DM_LOCAL_VERSION:-}" ]; then
  version=$DM_LOCAL_VERSION
  case "$version" in v*) ;; *) version="v$version" ;; esac
  release="$REPO/releases/download/$version"
else
  release="$REPO/releases/latest/download"
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$HOME/.local/bin" "$HOME/.decisionmodels/bin" "$HOME/.decisionmodels/runtimes"

get() { curl -fLsS "$1" -o "$2"; }
sha_of() { awk -v file="$2" '$2 == file || $2 == "*" file { print $1; exit }' "$1"; }
sha_check() {
  if command -v sha256sum >/dev/null 2>&1; then echo "$1  $2" | sha256sum -c - >/dev/null
  elif command -v shasum >/dev/null 2>&1; then echo "$1  $2" | shasum -a 256 -c - >/dev/null
  else echo "Need sha256sum or shasum to verify downloads." >&2; exit 1; fi
}

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' >/dev/null 2>&1; then
    py=$(command -v "$candidate")
    break
  fi
done

if [ -z "$py" ]; then
  get "$release/pins.py" "$tmp/pins.py"
  uv_version=$(sed -n 's/^UV_VERSION = "\([^"]*\)"/\1/p' "$tmp/pins.py")
  uv_release=$(sed -n 's/^UV_RELEASE = "\([^"]*\)"/\1/p' "$tmp/pins.py")
  [ -n "$uv_version" ] && [ -n "$uv_release" ] || { echo "Release does not contain uv pin metadata." >&2; exit 1; }
  system=$(uname -s); arch=$(uname -m)
  case "$system/$arch" in
    Linux/x86_64|Linux/amd64) uvfile="uv-x86_64-unknown-linux-gnu.tar.gz"; uvkey="x86_64-unknown-linux-gnu" ;;
    Linux/aarch64|Linux/arm64) uvfile="uv-aarch64-unknown-linux-gnu.tar.gz"; uvkey="aarch64-unknown-linux-gnu" ;;
    Darwin/arm64|Darwin/aarch64) uvfile="uv-aarch64-apple-darwin.tar.gz"; uvkey="aarch64-apple-darwin" ;;
    Darwin/x86_64) uvfile="uv-x86_64-apple-darwin.tar.gz"; uvkey="x86_64-apple-darwin" ;;
    *) echo "No pinned uv bootstrap for $system/$arch." >&2; exit 1 ;;
  esac
  pin_line=$(grep -nF "\"$uvkey\"" "$tmp/pins.py" | head -1 | cut -d: -f1)
  [ -n "$pin_line" ] || { echo "No uv pin for $uvkey." >&2; exit 1; }
  sha_line=$((pin_line + 2))
  uv_sha=$(sed -n "${sha_line}p" "$tmp/pins.py" | sed -E 's/.*"sha256": "([0-9a-f]{64})".*/\1/')
  [ -n "$uv_sha" ] || { echo "No official checksum for $uvfile." >&2; exit 1; }
  get "$uv_release/$uvfile" "$tmp/$uvfile"
  sha_check "$uv_sha" "$tmp/$uvfile"
  tar -xzf "$tmp/$uvfile" -C "$tmp"
  uv_bin=$(find "$tmp" -type f -name uv -print -quit)
  [ -n "$uv_bin" ] || { echo "Verified uv archive did not contain uv." >&2; exit 1; }
  cp "$uv_bin" "$HOME/.decisionmodels/bin/uv"
  chmod 755 "$HOME/.decisionmodels/bin/uv"
  "$HOME/.decisionmodels/bin/uv" python install 3.12
  uv_mode=1
else
  uv_mode=0
fi

get "$release/dm-local.pyz" "$tmp/dm-local.pyz"
get "$release/SHA256SUMS" "$tmp/SHA256SUMS"
expected=$(sha_of "$tmp/SHA256SUMS" "dm-local.pyz")
[ -n "$expected" ] || { echo "dm-local.pyz is missing from SHA256SUMS." >&2; exit 1; }
sha_check "$expected" "$tmp/dm-local.pyz"
if command -v cosign >/dev/null 2>&1; then
  get "$release/dm-local.pyz.sigstore.json" "$tmp/dm-local.pyz.sigstore.json"
  cosign verify-blob --bundle "$tmp/dm-local.pyz.sigstore.json" \
    --certificate-identity-regexp '^https://github.com/fstandhartinger/decisionmodels-local/' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com "$tmp/dm-local.pyz" >/dev/null
fi
cp "$tmp/dm-local.pyz" "$HOME/.decisionmodels/bin/dm-local.pyz"
if [ "$uv_mode" -eq 1 ]; then
  cat > "$HOME/.local/bin/dm-local" <<'WRAPPER'
#!/bin/sh
# installed by dm-local bootstrap
exec "$HOME/.decisionmodels/bin/uv" run --no-project --python 3.12 python "$HOME/.decisionmodels/bin/dm-local.pyz" "$@"
WRAPPER
else
  cat > "$HOME/.local/bin/dm-local" <<WRAPPER
#!/bin/sh
# installed by dm-local bootstrap
exec "$py" "$HOME/.decisionmodels/bin/dm-local.pyz" "\$@"
WRAPPER
fi
chmod 755 "$HOME/.local/bin/dm-local"
echo "Installed dm-local in $HOME/.local/bin. Add that directory to PATH if needed."
echo "Next: dm-local doctor; dm-local list"
if [ "$#" -gt 0 ]; then "$HOME/.local/bin/dm-local" "$@"; fi
