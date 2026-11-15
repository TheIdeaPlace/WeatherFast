#!/usr/bin/env python3
"""
weatherkit_rest.py — minimal WeatherKit REST client for the data harness.

Uses the same WeatherKit backend as the app's Swift framework, via
https://weatherkit.apple.com/. Auth is an ES256 JWT signed with a WeatherKit
key from the Apple Developer portal. Stdlib-only; signing shells out to the
system openssl (DER signature converted to the raw r||s JOSE form).

Credentials (never committed): weatherkit.json in the signing kit,
$SIGNING_KIT (default ~/.signing-kit), or ~/.fastweather-keys/weatherkit.json
if the kit doesn't have one. Restore the kit on a new Mac with
`python3 <projects repo>/signing/sync-secrets.py pull-kit`.
    {
      "team_id":    "<10-char team id>",
      "key_id":     "<10-char key id>",
      "service_id": "com.weatherfast.app",
      "p8_path":    "~/.fastweather-keys/AuthKey_<keyid>.p8"
    }
The key file is looked for in the kit folder under p8_path's file name first,
then at p8_path itself, so the same weatherkit.json works from either place.
If the config or key is missing, is_configured() returns False and callers
should skip WeatherKit sampling gracefully.

Calls draw from the same 500k requests/month WeatherKit allowance as the app.
"""

import base64
import json
import os
import subprocess
import time
import urllib.request

KIT = os.path.expanduser(os.environ.get("SIGNING_KIT") or "~/.signing-kit")
OLD_CONFIG_PATH = os.path.expanduser("~/.fastweather-keys/weatherkit.json")
CONFIG_PATH = os.path.join(KIT, "weatherkit.json")
if not os.path.isfile(CONFIG_PATH):
    CONFIG_PATH = OLD_CONFIG_PATH
_token_cache = {"token": None, "expires": 0}


def key_path(cfg):
    """The WeatherKit .p8: the kit's copy under p8_path's file name, else p8_path."""
    in_kit = os.path.join(KIT, os.path.basename(os.path.expanduser(cfg["p8_path"])))
    return in_kit if os.path.isfile(in_kit) else os.path.expanduser(cfg["p8_path"])


def is_configured():
    if not os.path.isfile(CONFIG_PATH):
        return False
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        return os.path.isfile(key_path(cfg))
    except Exception:  # noqa: BLE001
        return False


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _der_to_raw(sig):
    # DER ECDSA-Sig-Value {r INTEGER, s INTEGER} -> 64-byte r||s
    assert sig[0] == 0x30
    i = 2
    assert sig[i] == 0x02
    l = sig[i + 1]
    r = sig[i + 2:i + 2 + l]
    i += 2 + l
    assert sig[i] == 0x02
    l = sig[i + 1]
    s = sig[i + 2:i + 2 + l]
    return (r.lstrip(b"\x00").rjust(32, b"\x00") +
            s.lstrip(b"\x00").rjust(32, b"\x00"))


def token():
    """Signed JWT, cached and re-minted a few minutes before expiry."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires"] - 300:
        return _token_cache["token"]
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    p8 = key_path(cfg)
    header = {"alg": "ES256", "kid": cfg["key_id"],
              "id": "%s.%s" % (cfg["team_id"], cfg["service_id"])}
    payload = {"iss": cfg["team_id"], "iat": int(now),
               "exp": int(now) + 3000, "sub": cfg["service_id"]}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode()) + "." +
                     _b64url(json.dumps(payload, separators=(",", ":")).encode()))
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", p8],
                         input=signing_input.encode(), capture_output=True,
                         check=True).stdout
    tok = signing_input + "." + _b64url(_der_to_raw(der))
    _token_cache.update(token=tok, expires=now + 3000)
    return tok


def fetch_weather(lat, lon, country="US", tz="GMT",
                  datasets="currentWeather,forecastNextHour", timeout=30):
    """Raw WeatherKit weather response dict, or raises on HTTP error."""
    url = ("https://weatherkit.apple.com/api/v1/weather/en/%.4f/%.4f"
           "?dataSets=%s&countryCode=%s&timezone=%s"
           % (lat, lon, datasets, country, tz))
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# WeatherKit conditionCode values that mean precipitation is falling.
# Mirrors the spirit of the app's "condition enum as sole authority for
# whether it is precipitating" (RadarService.fetchWeatherKitNowcast).
PRECIPITATING_CONDITIONS = {
    "Drizzle", "FreezingDrizzle", "FreezingRain", "HeavyRain", "Rain",
    "SunShowers", "IsolatedThunderstorms", "ScatteredThunderstorms",
    "Thunderstorms", "StrongStorms", "Hail", "MixedRainAndSleet",
    "MixedRainAndSnow", "MixedRainfall", "MixedSnowAndSleet", "Sleet",
    "Snow", "HeavySnow", "Flurries", "SunFlurries", "WintryMix",
    "BlowingSnow", "Blizzard",
}


def centre_nowcast(lat, lon, country="US"):
    """The harness's view of what the app's WeatherKit path sees at a point.

    Returns None when WeatherKit is unreachable, or a dict:
      condition        — conditionCode string ("Cloudy", "Rain", ...)
      is_precipitating — condition-based, like the app's effectiveIsPrecip
      intensity_now    — currentWeather.precipitationIntensity (mm/h)
      minutes          — [(offset_min, mm_per_hr, active), ...] for the
                         next-hour forecast, offsets from the first minute;
                         active = intensity > 0 (REST minutes carry no
                         precipitation-type field, a documented
                         approximation of the Swift path)
      has_next_hour    — whether forecastNextHour minutes were returned
    """
    d = fetch_weather(lat, lon, country=country)
    cw = d.get("currentWeather") or {}
    condition = cw.get("conditionCode", "")
    minutes_raw = (d.get("forecastNextHour") or {}).get("minutes") or []
    minutes = []
    for i, m in enumerate(minutes_raw):
        mmhr = m.get("precipitationIntensity") or 0.0
        minutes.append((i, mmhr, mmhr > 0))
    return dict(
        condition=condition,
        is_precipitating=condition in PRECIPITATING_CONDITIONS,
        intensity_now=cw.get("precipitationIntensity") or 0.0,
        minutes=minutes,
        has_next_hour=bool(minutes),
    )


if __name__ == "__main__":
    import sys
    lat = float(sys.argv[1]) if len(sys.argv) > 2 else 43.0870
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else -89.3120
    if not is_configured():
        sys.exit("Not configured — see module docstring.")
    print(json.dumps(centre_nowcast(lat, lon), indent=2)[:800])
