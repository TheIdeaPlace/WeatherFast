"""Places of the World: curated lists of famous places (bridges, beaches,
extreme-weather spots) from the bundled ``places-of-the-world.json``.

The file is shared with iOS and the web app (CityData/ is the source):
``{"categories": [{"name", "description", "places": [{name, description,
city, state, country, lat, lon}, ...]}, ...]}``. ``city`` and ``state`` may be
missing or null, for example for an Antarctic station.

Kept free of wx so it can be tested.
"""

from .city_data import _load_first

FILENAME = "places-of-the-world.json"


def parse_categories(data):
    """The usable categories in a loaded file, in file order.

    A category without a name, or a place without a name or numeric
    coordinates, is skipped rather than breaking Browse.
    """
    out = []
    if not isinstance(data, dict):
        return out
    for cat in data.get("categories") or []:
        if not isinstance(cat, dict) or not cat.get("name"):
            continue
        places = []
        for p in cat.get("places") or []:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            try:
                lat, lon = float(p["lat"]), float(p["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            places.append(dict(p, lat=lat, lon=lon))
        out.append({"name": cat["name"],
                    "description": cat.get("description") or "",
                    "places": places})
    return out


def load_categories():
    """The bundled categories, or [] when the file is missing or unreadable."""
    return parse_categories(_load_first(FILENAME))


def location_line(place):
    """Where a place is: "San Francisco, California, United States", or just
    "Antarctica" when there's no town or state."""
    parts = [place.get("city"), place.get("state"), place.get("country")]
    return ", ".join(p for p in parts if p)


def saved_name(place):
    """The name a place gets in Your Cities, as on iOS: "Golden Gate Bridge,
    San Francisco", or just the name when there's no town (or the town is
    the place's own name)."""
    name = place["name"]
    city = place.get("city")
    return f"{name}, {city}" if city and city != name else name


def about_text(place):
    """What a row says after the weather: where it is, then why it's known."""
    parts = [location_line(place), (place.get("description") or "").strip()]
    return ". ".join(p for p in parts if p)


# Countries NWS alerts cover, as the data names them
NWS_COUNTRIES = frozenset({"United States", "Puerto Rico", "United States Virgin Islands"})


def is_nws_place(place):
    """Whether NWS alerts cover a place (a browse row or a place dict)."""
    return place.get("country") in NWS_COUNTRIES


def category_label(category):
    """How a list reads in the chooser: "Famous Bridges (153 places)"."""
    n = len(category["places"])
    return f"{category['name']} ({n} place{'' if n == 1 else 's'})"
