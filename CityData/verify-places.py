#!/usr/bin/env python3
"""
Check places-of-the-world.json for mistakes before distributing it.

- Structure: required fields, coordinate ranges, at most 200 places per category,
  no duplicate names or coordinates within a category.
- Country: reverse geocodes every place with Nominatim (1 request per second,
  per its usage policy) and reports places whose coordinates land in a different
  country than the entry says.
- Position: searches Nominatim for each place by name and reports places more
  than 15 km from the match. Places Nominatim can't find are listed separately
  for a manual look; that's common for weather stations and small beaches.
Lookups are cached in verify-places-cache.json, so re-runs only look up new or
moved places.

Usage:
    python3 verify-places.py                # check places-of-the-world.json
    python3 verify-places.py --offline      # structure checks only
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "places-of-the-world.json")
CACHE = os.path.join(HERE, "verify-places-cache.json")
MAX_PER_CATEGORY = 200
MAX_DISTANCE_KM = 15
USER_AGENT = "WeatherFast-CityData/1.0 (https://weatherfast.online)"

# Nominatim's English country names that differ from the names used in the data
COUNTRY_ALIASES = {
    "united states of america": "united states",
    "people's republic of china": "china",
    "the netherlands": "netherlands",
    "czechia": "czech republic",
    "türkiye": "turkey",
    "republic of korea": "south korea",
    "south korea": "south korea",
    "viet nam": "vietnam",
    "russian federation": "russia",
}


# Territories Nominatim reports under the country they belong to
TERRITORIES = {
    "puerto rico": "united states",
    "united states virgin islands": "united states",
    "guam": "united states",
    "hong kong": "china",
    "macau": "china",
    "french polynesia": "france",
    "new caledonia": "france",
    "french southern and antarctic lands": "france",
    "reunion": "france",
    "guadeloupe": "france",
    "martinique": "france",
    "aruba": "netherlands",
    "sint maarten": "netherlands",
    "curacao": "netherlands",
    "bermuda": "united kingdom",
    "british virgin islands": "united kingdom",
    "cayman islands": "united kingdom",
    "turks and caicos islands": "united kingdom",
    "anguilla": "united kingdom",
    "gibraltar": "united kingdom",
    "falkland islands": "united kingdom",
    "greenland": "denmark",
    "faroe islands": "denmark",
    "svalbard": "norway",
}


def same_country(found, expected):
    f, e = norm(found), norm(expected)
    return f == e or TERRITORIES.get(e) == f


def distance_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def norm(country):
    c = (country or "").strip().lower()
    return COUNTRY_ALIASES.get(c, c)


def structure_problems(data):
    problems = []
    for cat in data.get("categories", []):
        name = cat.get("name", "?")
        places = cat.get("places", [])
        if not cat.get("description"):
            problems.append(f"{name}: category has no description")
        if len(places) > MAX_PER_CATEGORY:
            problems.append(f"{name}: {len(places)} places, more than {MAX_PER_CATEGORY}")
        seen_names, seen_coords = set(), set()
        for p in places:
            label = f"{name} / {p.get('name', '?')}"
            for field in ("name", "description", "country", "lat", "lon"):
                if p.get(field) in (None, ""):
                    problems.append(f"{label}: missing {field}")
            lat, lon = p.get("lat"), p.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    problems.append(f"{label}: coordinates out of range")
                key = (round(lat, 3), round(lon, 3))
                if key in seen_coords:
                    problems.append(f"{label}: same coordinates as another place")
                seen_coords.add(key)
            if p.get("name") in seen_names:
                problems.append(f"{label}: duplicate name")
            seen_names.add(p.get("name"))
    return problems


def nominatim(endpoint, params):
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/{endpoint}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.load(resp)
    time.sleep(1.1)
    return result


def search_position(place):
    """First Nominatim match for the place's name, or None."""
    queries = [", ".join(x for x in (place["name"], place.get("city"), place.get("state"), place["country"]) if x),
               f"{place['name']}, {place['country']}"]
    for q in dict.fromkeys(queries):
        hits = nominatim("search", {"q": q, "format": "jsonv2", "limit": 1, "accept-language": "en"})
        if hits:
            return [float(hits[0]["lat"]), float(hits[0]["lon"])]
    return None


def reverse_country(lat, lon):
    query = urllib.parse.urlencode({
        "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 5, "accept-language": "en",
    })
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/reverse?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.load(resp)
    return result.get("address", {}).get("country")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="skip the Nominatim country check")
    args = parser.parse_args()

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    problems = structure_problems(data)
    for cat in data["categories"]:
        print(f"{cat['name']}: {len(cat['places'])} places")

    if not args.offline:
        cache = {}
        if os.path.exists(CACHE):
            with open(CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        for cat in data["categories"]:
            for p in cat["places"]:
                key = f"{p['lat']:.4f},{p['lon']:.4f}"
                if key not in cache:
                    try:
                        cache[key] = reverse_country(p["lat"], p["lon"])
                    except Exception as e:  # network trouble: report and keep going
                        print(f"  lookup failed for {p['name']}: {e}", file=sys.stderr)
                        continue
                    time.sleep(1.1)
                    with open(CACHE, "w", encoding="utf-8") as f:
                        json.dump(cache, f, indent=1)
                found = cache[key]
                expected = p["country"]
                if found is None:
                    if expected != "Antarctica":
                        problems.append(f"{cat['name']} / {p['name']}: coordinates resolve to no country (open water?)")
                elif not same_country(found, expected):
                    problems.append(f"{cat['name']} / {p['name']}: entry says {expected}, coordinates are in {found}")

        not_found = []
        for cat in data["categories"]:
            for p in cat["places"]:
                key = "search:" + "|".join(str(p.get(k) or "") for k in ("name", "city", "state", "country"))
                if key not in cache:
                    try:
                        cache[key] = search_position(p)
                    except Exception as e:
                        print(f"  search failed for {p['name']}: {e}", file=sys.stderr)
                        continue
                    with open(CACHE, "w", encoding="utf-8") as f:
                        json.dump(cache, f, indent=1)
                hit = cache[key]
                if hit is None:
                    not_found.append(f"{cat['name']} / {p['name']}")
                    continue
                km = distance_km(p["lat"], p["lon"], hit[0], hit[1])
                if km > MAX_DISTANCE_KM:
                    problems.append(f"{cat['name']} / {p['name']}: {km:.0f} km from the map's position ({hit[0]:.4f}, {hit[1]:.4f})")
        if not_found:
            print(f"\nNot found by name ({len(not_found)}), check by hand:")
            for line in not_found:
                print(f"  {line}")

    if problems:
        print(f"\n{len(problems)} problems:")
        for line in problems:
            print(f"  {line}")
        sys.exit(1)
    print("\nNo problems found.")


if __name__ == "__main__":
    main()
