#!/usr/bin/env bash
#
# setup-release-secrets.sh: retired.
#
# This script used to base64 a local App Store Connect key and an Apple
# Distribution .p12 and set them as WeatherFast repo secrets with `gh secret set`.
# It no longer does anything, on purpose:
#
# - The signing secrets ios-release.yml uses (ASC_KEY_ID, ASC_ISSUER_ID,
#   ASC_KEY_P8_BASE64, DIST_CERT_P12_BASE64, DIST_CERT_PASSWORD) are now
#   TheIdeaPlace organization secrets. They are set from the signing kit (Azure
#   Key Vault theideaplace-kit) by sync-secrets.py in the projects repo. A repo
#   secret with the same name would override them, so don't set these per repo.
# - ~/.fastweather-keys/ is retired, and the key that lived there is revoked.
#
# The file is kept, rather than deleted, so the old Desktop launcher
# ("Setup FastWeather Release Secrets.command") says where to go instead of
# failing with "no such file".

cat >&2 <<'EOF'
setup-release-secrets.sh is retired. It sets nothing.

WeatherFast's iOS signing secrets are TheIdeaPlace organization secrets now,
set from the signing kit in Azure Key Vault. To check or (re)set them, from any
computer signed in with `az login` and `gh auth login`:

  python3 <projects repo>/signing/sync-secrets.py
  python3 <projects repo>/signing/sync-secrets.py --apply --repo WeatherFast

The guide: https://github.com/kellylford/The-Idea-Place-Projects/blob/main/signing/README.md

The optional OPENMETEO_API_KEY secret isn't a signing secret, so the kit doesn't
manage it. To set it, run this in the Terminal app and paste the key when asked:

  gh secret set OPENMETEO_API_KEY -R TheIdeaPlace/WeatherFast
EOF
exit 1
