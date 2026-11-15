#!/usr/bin/env bash
#
# release-testflight.sh — one-command FastWeather iOS TestFlight release.
#
# Archives the app, exports a signed App Store IPA, uploads it to App Store
# Connect, waits for processing, then sets the What-to-Test notes, assigns the
# beta groups, and submits external Beta App Review.
#
# Credentials come from the signing kit (see scripts/RELEASE.md):
#   ASC_KEY_PATH   App Store Connect API key (.p8)
#                  default: $SIGNING_KIT/asc-api-key.p8, where SIGNING_KIT
#                  defaults to ~/.signing-kit (restore it with
#                  `python3 <projects repo>/signing/sync-secrets.py pull-kit`)
#   ASC_KEY_ID     default 38ANZ53D9L
#   ASC_ISSUER_ID  default d36bb41d-a198-401d-b36c-2e4fd15163e1
#   ASC_PY         path to the App Store Connect REST client (asc.py), which
#                  is not in this repo. Needed for TestFlight wiring, not for
#                  --upload-only.
#
# Usage:
#   scripts/release-testflight.sh --notes RELEASE_NOTES.txt
#   scripts/release-testflight.sh --notes notes.txt --groups "Internal test,External"
#   scripts/release-testflight.sh --notes notes.txt --no-external-review
#   scripts/release-testflight.sh --wire-only --version 1.5.9 --build 4 --notes notes.txt
#       (skip build/upload; just wire an already-uploaded build — e.g. one you
#        uploaded from Xcode)
#
set -euo pipefail

# --- locate repo/iOS dir (script lives in iOS/scripts) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SIGNING_KIT="${SIGNING_KIT:-$HOME/.signing-kit}"
ASC_KEY_PATH="${ASC_KEY_PATH:-$SIGNING_KIT/asc-api-key.p8}"
KEY_ID="${ASC_KEY_ID:-38ANZ53D9L}"
ISSUER="${ASC_ISSUER_ID:-d36bb41d-a198-401d-b36c-2e4fd15163e1}"
ASC="${ASC_PY:-}"

PROJECT="$IOS_DIR/FastWeather.xcodeproj"
SCHEME="FastWeather"
CONFIG="Release"
BUILD_DIR="$IOS_DIR/build/release"
EXPORT_PLIST="$SCRIPT_DIR/ExportOptions.plist"

# --- defaults ---
NOTES=""
# NB: not "GROUPS" — that is a reserved bash array (current user's group IDs).
BETA_GROUPS="Internal test,External"
SUBMIT_EXTERNAL=1
WIRE_ONLY=0
UPLOAD_ONLY=0
VERSION=""
BUILD=""

die() { echo "❌ $*" >&2; exit 1; }
step() { echo ""; echo "▶ $*"; }

# --- parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --notes) NOTES="$2"; shift 2;;
    --groups) BETA_GROUPS="$2"; shift 2;;
    --no-external-review) SUBMIT_EXTERNAL=0; shift;;
    --wire-only) WIRE_ONLY=1; shift;;
    --upload-only) UPLOAD_ONLY=1; shift;;
    --version) VERSION="$2"; shift 2;;
    --build) BUILD="$2"; shift 2;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

if [[ "$WIRE_ONLY" -eq 0 ]]; then
  [[ -f "$ASC_KEY_PATH" ]] || die "App Store Connect key not found at $ASC_KEY_PATH. Restore the signing kit with: python3 <projects repo>/signing/sync-secrets.py pull-kit (or set ASC_KEY_PATH)"
fi
if [[ "$UPLOAD_ONLY" -eq 0 ]]; then
  [[ -n "$ASC" ]] || die "set ASC_PY to the path of the App Store Connect client (asc.py) for TestFlight wiring, or pass --upload-only"
  [[ -f "$ASC" ]] || die "ASC_PY points at $ASC, which doesn't exist"
fi
# Notes are the TestFlight What-to-Test text; not needed for --upload-only.
if [[ "$UPLOAD_ONLY" -eq 0 ]]; then
  [[ -n "$NOTES" ]] || die "--notes <file> is required (the What-to-Test text)"
  NOTES="$(cd "$(dirname "$NOTES")" && pwd)/$(basename "$NOTES")"   # absolutize
  [[ -f "$NOTES" ]] || die "notes file not found: $NOTES"
  [[ -s "$NOTES" ]] || die "notes file is empty: $NOTES"
fi

# Hand the kit's key details to asc.py too, in case it reads them from the
# environment rather than its own config.
export ASC_KEY_ID="$KEY_ID" ASC_ISSUER_ID="$ISSUER" ASC_KEY_PATH

wire_testflight() {
  local ver="$1" bld="$2"
  local args=(testflight --version "$ver" --build "$bld" --notes-file "$NOTES" --groups "$BETA_GROUPS")
  [[ "$SUBMIT_EXTERNAL" -eq 0 ]] && args+=(--no-submit-external)
  step "Wiring TestFlight (notes + groups + review) for $ver ($bld)"
  python3 "$ASC" "${args[@]}"
}

# --- wire-only fast path (build already uploaded, e.g. from Xcode) ---
if [[ "$WIRE_ONLY" -eq 1 ]]; then
  [[ -n "$VERSION" && -n "$BUILD" ]] || die "--wire-only requires --version and --build"
  wire_testflight "$VERSION" "$BUILD"
  echo ""; echo "✅ Done (wire-only)."
  exit 0
fi

# --- read version/build from the project ---
step "Reading version from project"
SETTINGS="$(xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" -showBuildSettings 2>/dev/null)"
VERSION="$(echo "$SETTINGS" | awk -F' = ' '/ MARKETING_VERSION /{print $2; exit}')"
BUILD="$(echo "$SETTINGS"   | awk -F' = ' '/ CURRENT_PROJECT_VERSION /{print $2; exit}')"
[[ -n "$VERSION" && -n "$BUILD" ]] || die "could not read MARKETING_VERSION / CURRENT_PROJECT_VERSION"
echo "  Version $VERSION (build $BUILD)"

ARCHIVE="$BUILD_DIR/FastWeather-$VERSION-$BUILD.xcarchive"
EXPORT_DIR="$BUILD_DIR/export-$VERSION-$BUILD"
rm -rf "$ARCHIVE" "$EXPORT_DIR"
mkdir -p "$BUILD_DIR"

# --- archive ---
step "Archiving ($CONFIG, generic iOS device)"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates clean archive

# --- export signed IPA ---
step "Exporting App Store IPA"
xcodebuild -exportArchive -archivePath "$ARCHIVE" \
  -exportOptionsPlist "$EXPORT_PLIST" -exportPath "$EXPORT_DIR" \
  -allowProvisioningUpdates

IPA="$(/usr/bin/find "$EXPORT_DIR" -maxdepth 1 -name '*.ipa' | head -1)"
[[ -n "$IPA" ]] || die "no .ipa produced in $EXPORT_DIR"
echo "  IPA: $IPA"

# --- validate then upload via altool ---
# altool finds the key by file name (AuthKey_<id>.p8) in a private_keys folder.
# Point it at a throwaway folder holding a link to the kit's key, so nothing
# has to be copied into ~/.appstoreconnect/private_keys.
ALTOOL_KEYS="$(mktemp -d "${TMPDIR:-/tmp}/fw-asc-keys.XXXXXX")"
trap 'rm -rf "$ALTOOL_KEYS"' EXIT
ln -s "$ASC_KEY_PATH" "$ALTOOL_KEYS/AuthKey_${KEY_ID}.p8"
export API_PRIVATE_KEYS_DIR="$ALTOOL_KEYS"

step "Validating with App Store Connect"
xcrun altool --validate-app --type ios --file "$IPA" \
  --apiKey "$KEY_ID" --apiIssuer "$ISSUER"

step "Uploading to App Store Connect"
xcrun altool --upload-app --type ios --file "$IPA" \
  --apiKey "$KEY_ID" --apiIssuer "$ISSUER"
echo "  Upload accepted; App Store Connect is now processing the build."

# --- upload-only stops here (e.g. App Store submission handled separately) ---
if [[ "$UPLOAD_ONLY" -eq 1 ]]; then
  echo ""
  echo "✅ Built + uploaded $VERSION ($BUILD). Skipped TestFlight wiring (--upload-only)."
  exit 0
fi

# --- wire TestFlight (polls until the build is VALID) ---
wire_testflight "$VERSION" "$BUILD"

echo ""
echo "✅ Release complete: $VERSION ($BUILD)"
echo "   Internal testers can install now; external testers after Beta App Review clears."
