#!/bin/bash
set -euo pipefail

: "${MACOS_CERTIFICATE_P12_BASE64:?Missing signing certificate}"
: "${MACOS_CERTIFICATE_PASSWORD:?Missing certificate password}"
: "${APPLE_ID:?Missing Apple account email}"
: "${APPLE_TEAM_ID:?Missing Apple team ID}"
: "${APPLE_APP_SPECIFIC_PASSWORD:?Missing notarization password}"
: "${RELEASE_VERSION:?Missing release version}"
: "${RUNNER_TEMP:?Run signing on the CI runner}"

signing_dir=$(mktemp -d "$RUNNER_TEMP/c100x-signing.XXXXXX")
keychain="$signing_dir/signing.keychain-db"
cleanup() {
    security delete-keychain "$keychain" >/dev/null 2>&1 || true
    rm -rf "$signing_dir"
}
trap cleanup EXIT
umask 077
keychain_password=$(openssl rand -hex 32)
echo "::add-mask::$keychain_password"
printf '%s' "$MACOS_CERTIFICATE_P12_BASE64" | base64 --decode > "$signing_dir/certificate.p12"
security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 3600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security import "$signing_dir/certificate.p12" -k "$keychain" -P "$MACOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple: -k "$keychain_password" "$keychain" >/dev/null
security list-keychains -d user -s "$keychain"

mise exec -- python packaging/sign.py .local/release/C100X --keychain "$keychain"
mise exec -- python packaging/smoke.py .local/release/C100X
dmg=".local/release/c100x-${RELEASE_VERSION}-macos-arm64.dmg"
mise exec -- python packaging/dmg.py .local/release/C100X "$dmg"
codesign --sign 'Developer ID Application:' --keychain "$keychain" --timestamp "$dmg"

credentials=(--apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_SPECIFIC_PASSWORD")
xcrun notarytool submit "$dmg" "${credentials[@]}" --wait --timeout 30m --output-format json > "$signing_dir/notarization.json"
cat "$signing_dir/notarization.json"
submission_id=$(jq -r '.id' "$signing_dir/notarization.json")
xcrun notarytool log "$submission_id" "${credentials[@]}" .local/release/notarization-log.json
jq -e '.status == "Accepted"' "$signing_dir/notarization.json" >/dev/null
xcrun stapler staple "$dmg"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
