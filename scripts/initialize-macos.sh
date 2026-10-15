#!/bin/bash
# Compatible with the Bash 3.2 shipped by macOS. No Homebrew or sudo required.

campus_node_version_ok() {
    [[ "$1" =~ ^v?22\.([0-9]+)\.[0-9]+$ ]] && (( BASH_REMATCH[1] >= 12 ))
}

campus_architecture() {
    case "$1" in
        arm64) printf '%s\n' arm64 ;;
        x86_64) printf '%s\n' x64 ;;
        *) printf 'Unsupported Mac architecture: %s\n' "$1" >&2; return 1 ;;
    esac
}

campus_download() (
    set -euo pipefail
    local url="$1" destination="$2" partial="$2.partial" attempt
    case "$url" in https://*) ;; *) printf 'Tool downloads require HTTPS.\n' >&2; exit 1 ;; esac
    # Bash 3.2 unwinds function-local variables before EXIT in $(...). Keep the
    # cleanup path in the subshell's environment rather than a local variable.
    CAMPUS_DOWNLOAD_PARTIAL="$partial"
    trap 'rm -f "$CAMPUS_DOWNLOAD_PARTIAL"' EXIT
    for attempt in 1 2 3; do
        printf 'Downloading %s (attempt %s/3)...\n' "${destination##*/}" "$attempt" >&2
        if curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 20 \
            --max-time 600 --output "$partial" "$url"; then
            mv -f "$partial" "$destination"
            exit 0
        fi
        rm -f "$partial"
        if [ "$attempt" -lt 3 ]; then sleep "$attempt"; fi
    done
    printf 'Tool download failed: %s. Check your connection and run again.\n' "$url" >&2
    exit 1
)

campus_verify_checksum() {
    local archive="$1" checksums="$2" expected actual
    expected=$(awk -v target="${archive##*/}" '
        { gsub(/\r/, ""); name=$2; sub(/^\*/, "", name)
          if (length($1)==64 && $1 !~ /[^[:xdigit:]]/ && (NF==1 || name==target)) {
              print tolower($1); exit
          }
        }' "$checksums")
    actual=$(/usr/bin/shasum -a 256 "$archive" | awk '{ print $1 }')
    if [ -z "$expected" ] || [ "$actual" != "$expected" ]; then
        printf 'SHA256 checksum verification failed for %s. Run again.\n' "${archive##*/}" >&2
        return 1
    fi
}

campus_install_archive() (
    set -euo pipefail
    local url="$1" checksum_url="$2" destination="$3" binary="$4"
    local parent downloads archive staging
    parent=$(dirname "$destination")
    downloads="$parent/downloads"
    mkdir -p "$downloads"
    archive="$downloads/${url##*/}"
    campus_download "$url" "$archive"
    campus_download "$checksum_url" "$archive.sha256"
    campus_verify_checksum "$archive" "$archive.sha256"
    staging=$(mktemp -d "$parent/.unpack.XXXXXX")
    CAMPUS_ARCHIVE_STAGING="$staging"
    trap 'rm -rf "$CAMPUS_ARCHIVE_STAGING"' EXIT
    tar -xzf "$archive" -C "$staging" --strip-components 1
    if [ ! -x "$staging/$binary" ]; then
        printf 'Downloaded archive is missing executable %s.\n' "$binary" >&2
        exit 1
    fi
    rm -rf "$destination"
    mv "$staging" "$destination"
    printf '%s\n' "$destination/$binary"
)

campus_node() {
    local tools="$1" architecture="$2" candidate version base
    for candidate in "$tools/node/bin/node" "$(command -v node || true)"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ] && [ -f "$(dirname "$candidate")/npm" ]; then
            if version=$("$candidate" --version 2>/dev/null) && campus_node_version_ok "$version"; then
                printf 'Using Node %s\n' "$version" >&2
                printf '%s\n' "$candidate"
                return 0
            fi
        fi
    done
    base='https://nodejs.org/dist/v22.23.3'
    campus_install_archive "$base/node-v22.23.3-darwin-$architecture.tar.gz" \
        "$base/SHASUMS256.txt" "$tools/node" bin/node
}

campus_uv_version_ok() {
    [[ "$1" =~ ^uv\ ([0-9]+)\.([0-9]+)\.([0-9]+) ]] &&
        (( BASH_REMATCH[1] > 0 || BASH_REMATCH[2] > 11 ||
           (BASH_REMATCH[2] == 11 && BASH_REMATCH[3] >= 19) ))
}

campus_uv() {
    local tools="$1" architecture="$2" candidate version target base url
    for candidate in "$tools/uv/uv" "$(command -v uv || true)"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            if version=$("$candidate" --version 2>/dev/null) && campus_uv_version_ok "$version"; then
                printf 'Using %s\n' "$version" >&2
                printf '%s\n' "$candidate"
                return 0
            fi
        fi
    done
    target=x86_64
    if [ "$architecture" = arm64 ]; then target=aarch64; fi
    base='https://releases.astral.sh/github/uv/releases/download/0.11.19'
    url="$base/uv-$target-apple-darwin.tar.gz"
    campus_install_archive "$url" "$url.sha256" "$tools/uv" uv
}

campus_bundle_ready() {
    local root="$1" ignore_state="${2:-0}" app
    if [ "$ignore_state" != 1 ] && [ -e "$root/.tools/macos-build-incomplete" ]; then return 1; fi
    app="$root/dist/desktop/课间助手.app/Contents"
    [ -x "$app/MacOS/CampusCompanion" ] &&
        [ -f "$app/Frameworks/libpython3.12.dylib" ] &&
        [ -f "$app/Resources/frontend/dist/index.html" ] &&
        [ -f "$app/Resources/extension/.output/chrome-mv3/manifest.json" ]
}

campus_require_project() {
    local root="$1" relative
    for relative in .env.example backend/uv.lock frontend/package-lock.json \
        extension/package-lock.json scripts/build-desktop.py scripts/package-desktop.py \
        config/scut-undergraduate-2026-10-14.json; do
        if [ ! -f "$root/$relative" ]; then
            printf 'Missing %s. Download and extract the complete repository first.\n' "$relative" >&2
            return 1
        fi
    done
}

campus_settings() {
    if [ ! -e "$1/.env" ] && [ ! -L "$1/.env" ]; then cp -n "$1/.env.example" "$1/.env"; fi
}

campus_run_step() {
    local step="$1" status
    shift
    printf '%s\n' "$step"
    "$@" || {
        status=$?
        printf '%s failed (exit code %s).\n' "$step" "$status" >&2
        return "$status"
    }
}

campus_build_project() (
    set -euo pipefail
    local root="$1" rebuild="$2" tools architecture node uv
    # Recheck under the lock: another initialization may have just finished.
    if [ "$rebuild" = 0 ] && campus_bundle_ready "$root"; then
        campus_settings "$root"
        exit 0
    fi
    campus_require_project "$root"
    cd "$root"
    tools="$root/.tools/macos"
    architecture=$(campus_architecture "$(uname -m)")
    printf 'Preparing Campus Companion (%s). First run requires internet and may take several minutes.\n' "$architecture"
    printf 'Existing settings and personal data will be preserved.\n'
    node=$(campus_node "$tools" "$architecture")
    uv=$(campus_uv "$tools" "$architecture")
    export PATH="$(dirname "$node"):$(dirname "$uv"):$PATH"
    export UV_CACHE_DIR="$tools/uv-cache"
    export UV_PYTHON_INSTALL_DIR="$tools/python"
    export UV_PYTHON_PREFERENCE=only-managed
    export UV_PYTHON_DOWNLOADS=automatic
    export UV_PROJECT_ENVIRONMENT="$root/backend/.venv"
    printf 'Initialization has not completed. Run the launcher again.\n' > "$root/.tools/macos-build-incomplete"
    campus_run_step '[1/3] Installing Python 3.12 and locked dependencies' \
        "$uv" sync --project backend --locked --python 3.12 --group desktop
    campus_run_step '[2/3] Building frontend, extension, and desktop application' \
        "$uv" run --project backend --no-sync python scripts/build-desktop.py
    if ! campus_bundle_ready "$root" 1; then
        printf 'The desktop build is incomplete. Run initialization again.\n' >&2
        exit 1
    fi
    campus_run_step '[3/3] Checking the packaged application' \
        env PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        "$root/dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion" --help
    campus_run_step '[3/3] Checking bundled time tools' \
        env PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        "$root/dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion" --time-mcp </dev/null
    campus_settings "$root"
    rm -f "$root/.tools/macos-build-incomplete"
    printf 'Initialization complete. Configure your own model connection in Settings.\n'
)

campus_launch() {
    "$1/dist/desktop/课间助手.app/Contents/MacOS/CampusCompanion" --data-dir "$1" --project
}

campus_main() (
    set -euo pipefail
    local rebuild=0 no_launch=0 locked=0 root script log statuses
    local locked_arguments=(--locked)
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --rebuild) rebuild=1; locked_arguments+=(--rebuild) ;;
            --no-launch) no_launch=1 ;;
            --locked) locked=1 ;;
            *) printf 'Unknown option: %s. Use --rebuild or --no-launch.\n' "$1" >&2; exit 1 ;;
        esac
        shift
    done
    if [ "$(uname -s)" != Darwin ]; then printf 'This initializer requires macOS.\n' >&2; exit 1; fi
    script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/initialize-macos.sh"
    root=$(cd "$(dirname "$script")/.." && pwd -P)
    if [ "$locked" = 1 ]; then campus_build_project "$root" "$rebuild"; exit 0; fi
    if [ "$rebuild" = 0 ] && campus_bundle_ready "$root"; then
        campus_settings "$root"
        if [ "$no_launch" = 0 ]; then campus_launch "$root"; fi
        exit 0
    fi
    campus_require_project "$root"
    mkdir -p "$root/.tools"
    log="$root/.tools/macos-initialize.log"
    printf '\nInitialization started: %s\n' "$(date)" >> "$log"
    set +e
    /usr/bin/lockf -k -s -t 0 "$root/.tools/macos-initialize.lock" \
        /bin/bash "$script" "${locked_arguments[@]}" 2>&1 | tee -a "$log"
    statuses=("${PIPESTATUS[@]}")
    set -e
    if [ "${statuses[0]}" -ne 0 ]; then
        if [ "${statuses[0]}" -eq 75 ]; then
            printf 'Initialization is already running. Wait for the other window to finish.\n' >&2
        fi
        printf 'Initialization failed. See %s. Fix the problem and run again.\n' "$log" >&2
        exit "${statuses[0]}"
    fi
    if [ "${statuses[1]}" -ne 0 ]; then printf 'Could not write initialization log.\n' >&2; exit 1; fi
    if [ "$no_launch" = 0 ]; then campus_launch "$root"; fi
)

if [ "${BASH_SOURCE[0]}" = "$0" ]; then campus_main "$@"; fi
