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

# Authenticate the manifest before trusting model installer or Python-bootstrap pins.
get "$release/SHA256SUMS" "$tmp/SHA256SUMS"
get "$release/SHA256SUMS.sigstore.json" "$tmp/SHA256SUMS.sigstore.json"
if command -v cosign >/dev/null 2>&1; then
  cosign_bin=$(command -v cosign)
else
  case "$(uname -s)/$(uname -m)" in
    Linux/x86_64|Linux/amd64) cosign_file=cosign-linux-amd64; cosign_sha=c956e5dfcac53d52bcf058360d579472f0c1d2d9b69f55209e256fe7783f4c74 ;;
    Linux/aarch64|Linux/arm64) cosign_file=cosign-linux-arm64; cosign_sha=bedac92e8c3729864e13d4a17048007cfafa79d5deca993a43a90ffe018ef2b8 ;;
    Darwin/arm64|Darwin/aarch64) cosign_file=cosign-darwin-arm64; cosign_sha=5fadd012ae6381a6a29ff86a7d39aa873878852f1073fc90b15995961ecfb084 ;;
    Darwin/x86_64) cosign_file=cosign-darwin-amd64; cosign_sha=4c3e7af8372d3ca3296e62fa56f23fcbb5721cc6ac1827900d398f110d7cd280 ;;
    *) echo 'No signature verifier for this OS/architecture.' >&2; exit 1 ;;
  esac
  get "https://github.com/sigstore/cosign/releases/download/v3.0.6/$cosign_file" "$tmp/cosign"
  sha_check "$cosign_sha" "$tmp/cosign"
  chmod 700 "$tmp/cosign"
  cosign_bin="$tmp/cosign"
fi
"$cosign_bin" verify-blob --bundle "$tmp/SHA256SUMS.sigstore.json" \
  --certificate-identity-regexp '^https://github.com/fstandhartinger/decisionmodels-local/\.github/workflows/release\.yml@refs/tags/v[0-9][^/]*$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com "$tmp/SHA256SUMS" >/dev/null

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' >/dev/null 2>&1; then
    py=$(command -v "$candidate")
    break
  fi
done

if [ -z "$py" ]; then
  get "$release/pins.py" "$tmp/pins.py"
  pins_sha=$(sha_of "$tmp/SHA256SUMS" "pins.py")
  [ -n "$pins_sha" ] || { echo 'pins.py is missing from the signed manifest.' >&2; exit 1; }
  sha_check "$pins_sha" "$tmp/pins.py"
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
  py=$("$HOME/.decisionmodels/bin/uv" python find 3.12)
  [ -n "$py" ] || { echo "Could not locate the installed Python runtime." >&2; exit 1; }
fi

get "$release/dm-local.pyz" "$tmp/dm-local.pyz"
expected=$(sha_of "$tmp/SHA256SUMS" "dm-local.pyz")
[ -n "$expected" ] || { echo "dm-local.pyz is missing from SHA256SUMS." >&2; exit 1; }
sha_check "$expected" "$tmp/dm-local.pyz"
cp "$tmp/dm-local.pyz" "$HOME/.decisionmodels/bin/dm-local.pyz"
cat > "$HOME/.local/bin/dm-local" <<WRAPPER
#!/bin/sh
# installed by dm-local bootstrap
exec "$py" "$HOME/.decisionmodels/bin/dm-local.pyz" "\$@"
WRAPPER
chmod 755 "$HOME/.local/bin/dm-local"
echo "Installed dm-local in $HOME/.local/bin. Add that directory to PATH if needed."
echo "Next: dm-local doctor; dm-local list"
if [ "$#" -gt 0 ]; then "$HOME/.local/bin/dm-local" "$@"; fi
