# FastWeather iOS — TestFlight release

> **For the full release guide — including the critical beta-macOS constraint and
> the App Store submission flow — read [`../RELEASING.md`](../RELEASING.md) first.**
> This file only covers the local TestFlight script's flags.

One command builds, uploads, and wires a new build into TestFlight — no Xcode
Organizer, no manual App Store Connect clicking.

## One-time setup

The App Store Connect API key comes from the **signing kit**, outside the repo
(never committed). See
[`signing/README.md`](https://github.com/kellylford/The-Idea-Place-Projects/blob/main/signing/README.md)
in the projects repo.

- **The key:** `~/.signing-kit/asc-api-key.p8`, key ID `38ANZ53D9L`, issuer ID
  `d36bb41d-a198-401d-b36c-2e4fd15163e1`. On a new Mac, restore the folder from
  the vault with `python3 <projects repo>/signing/sync-secrets.py pull-kit`. The
  script uses those values by default; override them with `ASC_KEY_PATH` (or
  `SIGNING_KIT` for the folder), `ASC_KEY_ID` and `ASC_ISSUER_ID`. It points
  `altool` at the key itself, so nothing goes in `~/.appstoreconnect/private_keys/`.
- **The client:** `asc.py`, the ASC REST client (signs its own ES256 JWT; stdlib +
  `cryptography`), isn't in this repo. Set `ASC_PY` to its path. It's needed for
  the TestFlight wiring, not for `--upload-only`.

`~/.fastweather-keys/` is retired, and the key that lived there is revoked. If
the key is ever rotated, it's replaced in the kit (see `signing/README.md`), and
the new key ID goes in `ASC_KEY_ID` until this script's default is updated.

## Cut a release

1. Bump the version/build in Xcode (or the pbxproj): `MARKETING_VERSION` and
   `CURRENT_PROJECT_VERSION`. Commit.
2. Edit `scripts/RELEASE_NOTES.txt` with this build's What-to-Test text.
3. Run:

   ```bash
   cd iOS
   scripts/release-testflight.sh --notes scripts/RELEASE_NOTES.txt
   ```

That archives (Release, automatic signing), exports a signed App Store IPA,
validates + uploads it via `altool`, waits for App Store Connect to finish
processing, then sets the notes, assigns the **Internal test** + **External**
groups, and submits external Beta App Review.

Internal testers get it immediately; external testers once review clears.

## Options

| Flag | Effect |
|------|--------|
| `--notes <file>` | **required** — path to the What-to-Test text |
| `--groups "A,B"` | which beta groups to assign (default `Internal test,External`) |
| `--no-external-review` | assign groups but don't submit for Beta App Review |
| `--wire-only --version X --build Y` | skip build/upload; just wire an already-uploaded build (e.g. one uploaded from Xcode) |
| `--upload-only` | build and upload, but skip the TestFlight wiring (doesn't need `asc.py`) |

## Just the TestFlight wiring

If you uploaded from Xcode and only want the notes/groups/review applied:

```bash
scripts/release-testflight.sh --wire-only --version 1.5.9 --build 4 \
  --notes scripts/RELEASE_NOTES.txt
```

## Inspect state

```bash
python3 "$ASC_PY" probe      # auth check
python3 "$ASC_PY" discover   # app, recent builds, beta groups
```

## Notes / gotchas

- Signing is **automatic** (team `P887QF74N8`); the script passes
  `-allowProvisioningUpdates` so xcodebuild fetches the distribution profile.
- Export uses `scripts/ExportOptions.plist` (method `app-store-connect`).
- Build artifacts go to `iOS/build/` (gitignored).
- `altool` is deprecated by Apple but still the supported CLI upload path; if it
  is ever removed, swap the upload step for `xcrun notarytool`'s successor or
  Transporter — the wiring step (`asc.py testflight`) is unaffected.
