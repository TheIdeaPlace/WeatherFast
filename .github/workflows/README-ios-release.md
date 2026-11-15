# iOS App Store Release via GitHub Actions

The [`ios-release.yml`](ios-release.yml) workflow builds and uploads a FastWeather
build to App Store Connect from a GitHub-hosted macOS runner.

**Why this exists:** building on a Mac that's on a **beta macOS** (or with a beta
Xcode/SDK) stamps the binary as "compiled with a beta product," and Apple rejects
those for the public App Store. GitHub's runners are always on released macOS +
released Xcode, so builds from here pass review. (TestFlight accepts beta-stamped
builds, which is why your local TestFlight path still works.)

The workflow even guards against this: it aborts if the runner's selected iOS SDK
or Xcode is a beta seed.

## Secrets

The signing secrets are **TheIdeaPlace organization secrets**, shared with
WeatherFast and Scores. Nobody sets them on this repo by hand any more, and a
repo secret with the same name would override the organization one, so don't add
one. They're set from Kelly's signing kit (Azure Key Vault `theideaplace-kit`) by
`sync-secrets.py --apply` in the projects repo. The guide, including renewing the
Distribution certificate, is
[`signing/README.md`](https://github.com/kellylford/The-Idea-Place-Projects/blob/main/signing/README.md).

What the workflow reads:

- `ASC_KEY_ID`: App Store Connect API key ID, `38ANZ53D9L`.
- `ASC_ISSUER_ID`: App Store Connect issuer ID.
- `ASC_KEY_P8_BASE64`: the `.p8` API key, base64. From the kit's `asc-api-key.p8`.
- `DIST_CERT_P12_BASE64`: the Apple Distribution certificate and its private key,
  base64. From the kit's `apple-distribution.p12`.
- `DIST_CERT_PASSWORD`: that `.p12`'s password, from the kit.
- `OPENMETEO_API_KEY` *(optional)*: the paid Open-Meteo key, the value in your
  local `Secrets.swift`. This one is a repo secret, set by hand, since it isn't a
  signing secret: run `gh secret set OPENMETEO_API_KEY` in the Terminal app and
  paste the key when asked. Omit it to ship the free tier.
- `AIRNOW_API_KEY` *(optional)*: the AirNow air quality key, also a repo secret
  set by hand the same way (`gh secret set AIRNOW_API_KEY`).

To check that the signing secrets are set and shared with this repo, run
`python3 <projects repo>/signing/sync-secrets.py` (it changes nothing).

## Running it

1. **Actions** tab → **iOS App Store Release** → **Run workflow**.
2. **Build number**: the next unused build for version 1.5.8. Build 4 is already
   consumed (it was uploaded before Apple rejected it), so use **5** or higher.
3. **Marketing version**: leave blank to keep `1.5.8`.
4. Run. On success the build appears in App Store Connect (Processing for ~5–15 min),
   after which you can submit it for App Store review. The `.ipa` is also saved as a
   run artifact.

## Notes

- Signing is automatic: the ASC API key lets `xcodebuild` create/download the App
  Store provisioning profiles for both the app and the widget; the imported `.p12`
  provides the distribution identity.
- The workflow sets the build/marketing number for that run only — it does **not**
  commit the change back. Bump the numbers in git separately when you want the repo
  default to move.
- **Cost:** free for public repos. For a private repo, macOS runner minutes bill at
  10× — a build is a few minutes, so cents per run.
