#!/usr/bin/env python3
"""Assemble data/geo.json — the atlas layer the page loads.

Four sources, strongest first:

  0. data/geo_hand.json  what a person read off the article, and what they
     ruled out; the only source a rebuild cannot undo
  1. data/geo_raw.json   what the referent's own Wikidata item says
  2. data/geo_deep.json  what the thing it belongs to says (one hop out)
  3. the dataset's own curated `rg` regions on mythology and folklore
     families, which name a culture area rather than a country

Output is deliberately small: a place table, and one row per referent pointing
into it, so ~1,500 pins cost a few tens of kilobytes rather than a megabyte.

    python3 -I tools/geobuild.py
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

# The curated culture areas, as a point someone would actually put a pin on.
# These are centroids of a cultural region, not of a country: "Norse &
# Germanic" sits over southern Scandinavia, not over the Arctic midpoint.
REGION_POINTS = {
    "Japan":                    (36.0, 138.0),
    "Korea":                    (36.6, 127.9),
    "China":                    (34.0, 108.9),
    "South & Southeast Asia":   (17.0, 92.0),
    "West Asia & Arabia":       (29.5, 45.0),
    "Abrahamic tradition":      (31.8, 35.2),
    "Egypt & North Africa":     (27.0, 29.0),
    "Sub-Saharan Africa":       (0.5, 22.0),
    "Greece & Rome":            (39.5, 19.5),
    "Iberia & Mediterranean":   (39.6, -3.8),
    "Western Europe":           (48.3, 4.0),
    "Celtic & British Isles":   (53.6, -6.8),
    "Norse & Germanic":         (59.5, 11.0),
    "Slavic & Eastern Europe":  (52.0, 27.0),
    "North America":            (43.0, -99.0),
    "Mesoamerica & Andes":      (12.0, -85.0),
    "Oceania & Polynesia":      (-17.0, 178.0),
    # "Not tied to one place" is exactly that — it gets no pin.
}

# Place names Wikidata hands back that are not where a reader would look.
# A continent-sized answer is still worth a pin; a planet is not.
SKIP_PLACES = {"Earth", "Solar System", "universe", "outer space", "Milky Way"}

# Wikidata's formal or historical name for a place a reader knows by another.
# Only exact synonyms of the same modern place: a genuinely historical polity
# (Manchukuo, the Holy Roman Empire) keeps its own name and its own pin.
ALIAS = {
    "People's Republic of China": "China",
    "Republic of China": "Taiwan",
    "Taiwan Island": "Taiwan",
    "United Kingdom of Great Britain and Ireland": "United Kingdom",
    "Kingdom of Great Britain": "United Kingdom",
    "Great Britain": "United Kingdom",
    "Kingdom of Denmark": "Denmark",
    "Kingdom of the Netherlands": "Netherlands",
    "Australian continent": "Australia",
    "Mauritius Island": "Mauritius",
    "Kingdom of Hawai\u02bbi": "Hawaii",
    "Nordic countries": "Scandinavia",
    "Ancient Egypt": "Egypt",
    "Ancient Greece": "Greece",
    "United States of America": "United States",
    "Soviet Union": "Russia",
    "Russian Empire": "Russia",
}


def load(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        print("missing %s — skipping" % name, file=sys.stderr)
        return default if default is not None else {}
    with open(path) as fh:
        return json.load(fh)


def main():
    D = load("map_data.json")
    hand = load("geo_hand.json", {})
    raw = load("geo_raw.json", {})
    deep = load("geo_deep.json", {})
    refs = D["referents"]
    placed_by_hand = hand.get("place") or {}
    unplaced_by_hand = hand.get("unplace") or {}

    # which cluster sits in which curated region, and so which referents do
    region_of_ref = {}
    for fam, f in D["families"].items():
        for region, clusters in (f.get("rg") or {}).items():
            if region not in REGION_POINTS:
                continue
            for cluster in clusters:
                # a region holds a top-level cluster; everything under it
                # inherits the region
                stack = [cluster]
                while stack:
                    c = stack.pop()
                    g = D["groups"].get(c)
                    if not g:
                        continue
                    for m in g.get("m") or []:
                        region_of_ref.setdefault(m, region)
                    stack.extend(g.get("ch") or [])

    places, index = [], {}

    def place_id(name, lat, lon, qid=None):
        # One pin per name: the same country reached two ways (its own claim,
        # or a culture area that happens to be a country) came back with
        # points a degree apart and drew two pins on top of each other.
        name = ALIAS.get(name, name)
        if name not in index:
            index[name] = len(places)
            # the Wikidata item for the place, so the panel can link what it
            # is claiming — a culture area is ours, and has none
            places.append([name, round(lat, 2), round(lon, 2), qid])
        elif qid and places[index[name]][3] is None:
            places[index[name]][3] = qid
        return index[name]

    vias, viaidx = [], {}

    def via_id(text):
        if text not in viaidx:
            viaidx[text] = len(vias)
            vias.append(text)
        return viaidx[text]

    out, counts = {}, {"direct": 0, "hop": 0, "region": 0, "hand": 0}
    for name in sorted(refs):
        hit, kind = None, None
        if name in unplaced_by_hand:
            continue              # audited and found to be from nowhere
        if name in placed_by_hand:
            h = placed_by_hand[name]
            hit, kind = {"lat": h["lat"], "lon": h["lon"], "place": h["place"],
                         "placeq": h.get("q"),
                         "via": "placed by hand after checking"}, "hand"
        elif name in raw and raw[name].get("place") not in SKIP_PLACES:
            hit, kind = raw[name], "direct"
        elif name in deep and deep[name].get("place") not in SKIP_PLACES:
            hit, kind = deep[name], "hop"
        elif name in region_of_ref:
            region = region_of_ref[name]
            lat, lon = REGION_POINTS[region]
            hit, kind = {"lat": lat, "lon": lon, "place": region,
                         "via": "filed under this culture area"}, "region"
        if not hit:
            continue
        counts[kind] += 1
        out[name] = [place_id(hit["place"], hit["lat"], hit["lon"],
                              hit.get("placeq") or (hit.get("q") if kind == "direct" else None)),
                     via_id(hit["via"]),
                     {"direct": 0, "hop": 1, "region": 2, "hand": 3}[kind]]

    # Pokémon reachable through placed referents, for the header count
    species = set()
    for name in out:
        species.update(refs[name].get("s") or [])

    why = {n: h["why"] for n, h in placed_by_hand.items()
           if n in out and h.get("why")}
    geo = {"places": places, "vias": vias, "refs": out, "why": why,
           "regions": sorted(REGION_POINTS),
           "meta": {"referents": len(out), "species": len(species),
                    "places": len(places), "build": D["meta"].get("build"),
                    "direct": counts["direct"], "hop": counts["hop"],
                    "region": counts["region"], "hand": counts["hand"]}}
    path = os.path.join(DATA, "geo.json")
    with open(path, "w") as fh:
        json.dump(geo, fh, separators=(",", ":"), sort_keys=True)
    print("wrote %s — %d KB" % (path, os.path.getsize(path) // 1024))
    print("%d referents placed (%d direct, %d one hop out, %d by culture area, "
          "%d by hand; %d suppressed by hand)"
          % (len(out), counts["direct"], counts["hop"], counts["region"],
             counts["hand"], len(unplaced_by_hand)))
    print("%d places, %d Pokémon reachable" % (len(places), len(species)))
    top = {}
    for name, row in out.items():
        p = places[row[0]][0]
        top[p] = top.get(p, 0) + 1
    for k, n in sorted(top.items(), key=lambda kv: -kv[1])[:12]:
        print("  %-28s %d" % (k, n))


if __name__ == "__main__":
    main()
