#!/usr/bin/env python3
"""App Store Connect API client for FastWeather TestFlight automation.

Signs an ES256 JWT with the App Store Connect API key using the `cryptography`
lib (no PyJWT needed) and talks to api.appstoreconnect.apple.com. The key comes
from the signing kit (see the projects repo's signing/README.md), like
release-testflight.sh:

  ASC_KEY_PATH   the .p8 key; default $SIGNING_KIT/asc-api-key.p8, where
                 SIGNING_KIT defaults to ~/.signing-kit (restore it with
                 `python3 <projects repo>/signing/sync-secrets.py pull-kit`)
  ASC_KEY_ID     default 38ANZ53D9L
  ASC_ISSUER_ID  default d36bb41d-a198-401d-b36c-2e4fd15163e1
  ASC_BUNDLE_ID  default com.weatherfast.app

Nothing here prints the key or the token.

Subcommands:
  check                 read-only: sign in and look up WeatherFast
  probe                 auth check — list visible apps
  discover              app + recent builds + beta groups
  testflight ...        wire an already-uploaded build into TestFlight:
                        set What-to-Test, assign beta groups, submit external review

Examples:
  python3 asc.py check
  python3 asc.py probe
  python3 asc.py discover
  python3 asc.py testflight --version 1.5.9 --build 4 \
      --notes-file /path/to/notes.txt \
      --groups "Internal test,External" --submit-external
"""
import os, sys, json, time, base64, argparse
from urllib import request, parse, error
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

KIT = os.path.expanduser(os.environ.get("SIGNING_KIT") or "~/.signing-kit")
P8 = os.path.expanduser(os.environ.get("ASC_KEY_PATH") or os.path.join(KIT, "asc-api-key.p8"))
KEY_ID = os.environ.get("ASC_KEY_ID") or "38ANZ53D9L"
ISSUER = os.environ.get("ASC_ISSUER_ID") or "d36bb41d-a198-401d-b36c-2e4fd15163e1"
BUNDLE = os.environ.get("ASC_BUNDLE_ID") or "com.weatherfast.app"
BASE = "https://api.appstoreconnect.apple.com"


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def make_token():
    if not os.path.isfile(P8):
        raise SystemExit(f"App Store Connect key not found at {P8}. Restore the signing kit with: "
                         "python3 <projects repo>/signing/sync-secrets.py pull-kit (or set ASC_KEY_PATH)")
    with open(P8, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    header = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": ISSUER, "iat": now, "exp": now + 19 * 60, "aud": "appstoreconnect-v1"}
    si = _b64(json.dumps(header, separators=(",", ":")).encode()) + b"." + \
         _b64(json.dumps(payload, separators=(",", ":")).encode())
    der = key.sign(si, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return (si + b"." + _b64(sig)).decode()


# Token is regenerated per-call cheaply; ES256 signing is fast and this avoids
# expiry during long build-processing polls.
def api(method, path, body=None, query=None, retries=4, timeout=30):
    url = BASE + path
    if query:
        url += "?" + parse.urlencode(query, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    last_err = None
    for attempt in range(retries):
        req = request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + make_token())
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except error.HTTPError as e:
            raw = e.read()
            try:
                j = json.loads(raw)
            except Exception:
                j = {"raw": raw.decode(errors="replace")}
            # Retry transient server-side errors; return everything else as-is.
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                last_err = (e.code, j)
                time.sleep(2 * (attempt + 1))
                continue
            return e.code, j
        except (error.URLError, TimeoutError) as e:
            # Network blip / handshake timeout — back off and retry.
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    # Exhausted retries on a transient HTTP status.
    if isinstance(last_err, tuple):
        return last_err


def find_app():
    st, j = api("GET", "/v1/apps", query={"filter[bundleId]": BUNDLE, "limit": 5})
    if st != 200:
        raise SystemExit(f"app lookup failed ({st}): {json.dumps(j)}")
    for a in j.get("data", []):
        if a["attributes"].get("bundleId") == BUNDLE:
            return a["id"]
    raise SystemExit(f"app not found for bundle {BUNDLE}")


def beta_groups(app_id):
    st, j = api("GET", "/v1/betaGroups", query={
        "filter[app]": app_id, "limit": 50,
        "fields[betaGroups]": "name,isInternalGroup",
    })
    if st != 200:
        raise SystemExit(f"beta groups fetch failed ({st}): {json.dumps(j)}")
    return {g["attributes"]["name"]: (g["id"], g["attributes"].get("isInternalGroup", False))
            for g in j.get("data", [])}


def find_build(app_id, version, build_number):
    """Return build dict matching marketing version + build number, or None."""
    st, j = api("GET", "/v1/builds", query={
        "filter[app]": app_id, "sort": "-uploadedDate", "limit": 20,
        "include": "preReleaseVersion",
        # NB: relationship names must be listed in the fieldset or the linkage
        # (relationships.preReleaseVersion.data) is omitted from the response.
        "fields[builds]": "version,processingState,uploadedDate,preReleaseVersion",
        "fields[preReleaseVersions]": "version",
    })
    if st != 200:
        raise SystemExit(f"builds fetch failed ({st}): {json.dumps(j)}")
    pre = {x["id"]: x["attributes"].get("version")
           for x in j.get("included", []) if x["type"] == "preReleaseVersions"}
    for b in j.get("data", []):
        prid = (b.get("relationships", {}).get("preReleaseVersion", {}).get("data") or {}).get("id")
        if b["attributes"].get("version") == str(build_number) and pre.get(prid) == version:
            return b
    return None


def poll_build(app_id, version, build_number, timeout=1800, interval=30):
    """Wait for the build to appear and reach VALID. Returns build id."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        b = find_build(app_id, version, build_number)
        if b:
            state = b["attributes"].get("processingState")
            if state != last:
                print(f"  build {version} ({build_number}): {state}")
                last = state
            if state == "VALID":
                return b["id"]
            if state in ("FAILED", "INVALID"):
                raise SystemExit(f"build processing {state}")
        else:
            if last is None:
                print(f"  waiting for build {version} ({build_number}) to appear in App Store Connect…")
                last = "PENDING"
        time.sleep(interval)
    raise SystemExit("timed out waiting for build to become VALID")


def set_whats_new(build_id, notes, locale="en-US"):
    st, j = api("GET", f"/v1/builds/{build_id}/betaBuildLocalizations",
                query={"fields[betaBuildLocalizations]": "locale,whatsNew"})
    loc_id = None
    for loc in j.get("data", []):
        if loc["attributes"].get("locale") == locale:
            loc_id = loc["id"]; break
    if loc_id:
        st, j = api("PATCH", f"/v1/betaBuildLocalizations/{loc_id}", body={
            "data": {"type": "betaBuildLocalizations", "id": loc_id,
                     "attributes": {"whatsNew": notes}}})
    else:
        st, j = api("POST", "/v1/betaBuildLocalizations", body={
            "data": {"type": "betaBuildLocalizations",
                     "attributes": {"locale": locale, "whatsNew": notes},
                     "relationships": {"build": {"data": {"type": "builds", "id": build_id}}}}})
    if st not in (200, 201):
        raise SystemExit(f"set whatsNew failed ({st}): {json.dumps(j)}")
    print(f"  What-to-Test set ({locale}).")


def assign_group(build_id, group_id, name):
    st, j = api("POST", f"/v1/betaGroups/{group_id}/relationships/builds",
                body={"data": [{"type": "builds", "id": build_id}]})
    if st in (200, 201, 204):
        print(f"  assigned to group '{name}'.")
    else:
        raise SystemExit(f"assign to '{name}' failed ({st}): {json.dumps(j)}")


def submit_external_review(build_id):
    # Skip if a submission already exists.
    st, j = api("GET", f"/v1/builds/{build_id}/betaAppReviewSubmission",
                query={"fields[betaAppReviewSubmissions]": "betaReviewState"})
    if st == 200 and j.get("data"):
        print(f"  external review already submitted: {j['data']['attributes'].get('betaReviewState')}")
        return
    st, j = api("POST", "/v1/betaAppReviewSubmissions", body={
        "data": {"type": "betaAppReviewSubmissions",
                 "relationships": {"build": {"data": {"type": "builds", "id": build_id}}}}})
    if st in (200, 201):
        print(f"  submitted for external beta review: {j['data']['attributes'].get('betaReviewState')}")
    else:
        raise SystemExit(f"beta review submission failed ({st}): {json.dumps(j)}")


# ---------------- App Store (public release) ----------------

def list_appstore_versions(app_id):
    st, j = api("GET", f"/v1/apps/{app_id}/appStoreVersions", query={
        "limit": 20, "include": "build",
        "fields[appStoreVersions]": "versionString,appStoreState,build",
        "fields[builds]": "version"})
    if st != 200:
        raise SystemExit(f"appStoreVersions fetch failed ({st}): {json.dumps(j)}")
    inc = {x["id"]: x["attributes"].get("version") for x in j.get("included", []) if x["type"] == "builds"}
    out = []
    for v in j.get("data", []):
        b = (v.get("relationships", {}).get("build", {}).get("data") or {})
        out.append({"id": v["id"], "versionString": v["attributes"].get("versionString"),
                    "state": v["attributes"].get("appStoreState"),
                    "build_id": b.get("id"), "build_num": inc.get(b.get("id"))})
    return out


def find_appstore_version(app_id, version_string):
    for v in list_appstore_versions(app_id):
        if v["versionString"] == version_string:
            return v
    return None


def rename_appstore_version(vid, new_version_string):
    return api("PATCH", f"/v1/appStoreVersions/{vid}", body={
        "data": {"type": "appStoreVersions", "id": vid,
                 "attributes": {"versionString": new_version_string}}})


def attach_build_to_appstore_version(vid, build_id):
    return api("PATCH", f"/v1/appStoreVersions/{vid}/relationships/build",
               body={"data": {"type": "builds", "id": build_id}})


def get_review_submissions(app_id):
    st, j = api("GET", "/v1/reviewSubmissions", query={"filter[app]": app_id, "limit": 20})
    if st != 200:
        raise SystemExit(f"reviewSubmissions fetch failed ({st}): {json.dumps(j)}")
    return [{"id": s["id"], "state": s["attributes"].get("state"),
             "platform": s["attributes"].get("platform")} for s in j.get("data", [])]


def cancel_review_submission(sub_id):
    return api("PATCH", f"/v1/reviewSubmissions/{sub_id}",
               body={"data": {"type": "reviewSubmissions", "id": sub_id,
                              "attributes": {"canceled": True}}})


def create_review_submission(app_id):
    return api("POST", "/v1/reviewSubmissions", body={
        "data": {"type": "reviewSubmissions", "attributes": {"platform": "IOS"},
                 "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}})


def add_review_item(sub_id, vid):
    return api("POST", "/v1/reviewSubmissionItems", body={
        "data": {"type": "reviewSubmissionItems",
                 "relationships": {
                     "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": sub_id}},
                     "appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}}}})


def submit_review_submission(sub_id):
    return api("PATCH", f"/v1/reviewSubmissions/{sub_id}",
               body={"data": {"type": "reviewSubmissions", "id": sub_id,
                              "attributes": {"submitted": True}}})


def cmd_testflight(args):
    app_id = find_app()
    print(f"App: {app_id} ({BUNDLE})")

    if args.build_id:
        build_id = args.build_id
        print(f"Using build id {build_id} (skipping poll).")
    else:
        build_id = poll_build(app_id, args.version, args.build,
                              timeout=args.timeout, interval=args.interval)
        print(f"Build VALID: {build_id}")

    if args.notes_file:
        notes = open(os.path.expanduser(args.notes_file)).read().strip()
        if not notes:
            raise SystemExit("notes file is empty")
        set_whats_new(build_id, notes, locale=args.locale)

    groups = beta_groups(app_id)
    wanted = [g.strip() for g in args.groups.split(",") if g.strip()]
    external_targeted = False
    for name in wanted:
        if name not in groups:
            raise SystemExit(f"beta group '{name}' not found. Available: {list(groups)}")
        gid, is_internal = groups[name]
        assign_group(build_id, gid, name)
        if not is_internal:
            external_targeted = True

    if external_targeted and args.submit_external:
        submit_external_review(build_id)
    print("TestFlight wiring complete.")


def main():
    p = argparse.ArgumentParser(description="FastWeather App Store Connect helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="read-only: sign in and look up WeatherFast")
    sub.add_parser("probe")
    sub.add_parser("discover")
    tf = sub.add_parser("testflight", help="wire an uploaded build into TestFlight")
    tf.add_argument("--version", help="marketing version, e.g. 1.5.9")
    tf.add_argument("--build", help="build number, e.g. 4")
    tf.add_argument("--build-id", dest="build_id", help="use a known build id, skip lookup/poll")
    tf.add_argument("--notes-file", help="path to What-to-Test text")
    tf.add_argument("--locale", default="en-US")
    tf.add_argument("--groups", default="Internal test,External")
    tf.add_argument("--submit-external", action="store_true", default=True)
    tf.add_argument("--no-submit-external", dest="submit_external", action="store_false")
    tf.add_argument("--timeout", type=int, default=1800)
    tf.add_argument("--interval", type=int, default=30)
    args = p.parse_args()

    if args.cmd == "check":
        print(f"Key {KEY_ID} from {P8}")
        print(f"App: {find_app()} ({BUNDLE})")
    elif args.cmd == "probe":
        st, j = api("GET", "/v1/apps", query={"limit": 200})
        if st != 200:
            print("AUTH FAILED", st, json.dumps(j, indent=2)); sys.exit(1)
        print("AUTH OK — visible apps:")
        for a in j.get("data", []):
            at = a["attributes"]
            print(f"  {a['id']}  {at.get('bundleId')}  \"{at.get('name')}\"")
    elif args.cmd == "discover":
        app_id = find_app()
        print(f"APP: {app_id}  ({BUNDLE})")
        st, j = api("GET", "/v1/builds", query={
            "filter[app]": app_id, "sort": "-uploadedDate", "limit": 8,
            "include": "preReleaseVersion",
            "fields[builds]": "version,uploadedDate,processingState,expired,preReleaseVersion",
            "fields[preReleaseVersions]": "version"})
        pre = {x["id"]: x["attributes"] for x in j.get("included", []) if x["type"] == "preReleaseVersions"}
        print("\n== Recent builds ==")
        for b in j.get("data", []):
            at = b["attributes"]
            prid = (b.get("relationships", {}).get("preReleaseVersion", {}).get("data") or {}).get("id")
            pv = pre.get(prid, {})
            print(f"  build_id={b['id']}  v{pv.get('version','?')} ({at.get('version')})  "
                  f"{at.get('processingState')}  uploaded={at.get('uploadedDate')}")
        print("\n== Beta groups ==")
        for name, (gid, internal) in beta_groups(app_id).items():
            print(f"  group_id={gid}  [{'INTERNAL' if internal else 'EXTERNAL'}]  \"{name}\"")
    elif args.cmd == "testflight":
        if not args.build_id and not (args.version and args.build):
            raise SystemExit("provide --version and --build, or --build-id")
        cmd_testflight(args)


if __name__ == "__main__":
    main()
