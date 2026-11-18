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

# The countries each culture area is drawn from, so the Atlas can shade it
# instead of dropping a dot at a centroid. 353 referents — 39% of every pin —
# sit on one of these, and a point is the wrong shape for all of them:
# "Greece & Rome" was a dot in the Ionian Sea and "Oceania & Polynesia" one
# near Fiji, for a region spanning a third of the planet.
#
# These are the core of each area, not the greatest extent it ever reached:
# the Roman empire ran to Hadrian's Wall, and shading Britain for it would
# fight the Celtic area for the same ground. No country is listed twice, so
# the shapes never overlap and a reader can trust the one they are looking at.
# Names are world.json's spellings, which is why "United States of America"
# and "Bosnia and Herz." look like that. Checked against it at build time.
AREA_COUNTRIES = {
    "Japan": ["Japan"],
    "Korea": ["North Korea", "South Korea"],
    "China": ["China"],
    "South & Southeast Asia": [
        "India", "Pakistan", "Bangladesh", "Nepal", "Bhutan", "Sri Lanka",
        "Myanmar", "Thailand", "Laos", "Cambodia", "Vietnam", "Malaysia",
        "Indonesia", "Philippines", "Brunei", "Timor-Leste"],
    "West Asia & Arabia": [
        "Saudi Arabia", "Yemen", "Oman", "United Arab Emirates", "Qatar",
        "Kuwait", "Iraq", "Iran", "Syria", "Turkey", "Afghanistan"],
    # where it began, not where it is practised — the whole point of shading
    # is to stop a pin claiming more than it should
    "Abrahamic tradition": ["Israel", "Palestine", "Jordan", "Lebanon"],
    "Egypt & North Africa": [
        "Egypt", "Libya", "Tunisia", "Algeria", "Morocco", "W. Sahara",
        "Sudan"],
    "Sub-Saharan Africa": [
        "Nigeria", "Ghana", "Mali", "Senegal", "Ethiopia", "Kenya",
        "Tanzania", "Uganda", "Dem. Rep. Congo", "Congo", "Cameroon",
        "Angola", "Zambia", "Zimbabwe", "Mozambique", "Botswana", "Namibia",
        "South Africa", "Somalia", "Chad", "Niger", "Burkina Faso", "Benin",
        "Togo", "Guinea", "Sierra Leone", "Liberia", "Côte d'Ivoire",
        "Gabon", "Central African Rep.", "S. Sudan", "Eritrea", "Rwanda",
        "Burundi", "Malawi", "Lesotho", "eSwatini", "Gambia",
        "Guinea-Bissau", "Mauritania", "Djibouti", "Eq. Guinea",
        "Somaliland", "Madagascar"],
    "Greece & Rome": ["Greece", "Italy"],
    "Iberia & Mediterranean": ["Spain", "Portugal", "Cyprus"],
    "Western Europe": [
        "France", "Germany", "Belgium", "Netherlands", "Luxembourg",
        "Switzerland", "Austria"],
    "Celtic & British Isles": ["Ireland", "United Kingdom"],
    # Finland is Nordic but not Germanic, and the Kalevala is its own thing
    "Norse & Germanic": ["Norway", "Sweden", "Denmark", "Iceland"],
    "Slavic & Eastern Europe": [
        "Russia", "Ukraine", "Belarus", "Poland", "Czechia", "Slovakia",
        "Hungary", "Romania", "Bulgaria", "Serbia", "Croatia", "Slovenia",
        "Bosnia and Herz.", "Montenegro", "Macedonia", "Kosovo", "Moldova",
        "Albania", "Lithuania", "Latvia", "Estonia"],
    # Mexico southward is Mesoamerica; this is the indigenous north
    "North America": ["United States of America", "Canada"],
    "Mesoamerica & Andes": [
        "Mexico", "Guatemala", "Belize", "Honduras", "El Salvador",
        "Nicaragua", "Costa Rica", "Panama", "Peru", "Bolivia", "Ecuador",
        "Colombia", "Chile"],
    # Polynesia proper is mostly islands too small for a 177-country world
    # map, so this shades what there is and the panel says as much
    "Oceania & Polynesia": [
        "New Zealand", "Fiji", "Vanuatu", "Solomon Is.", "Papua New Guinea",
        "New Caledonia"],
}

# Place names Wikidata hands back that are not where a reader would look.
# A continent-sized answer is still worth a pin; a planet is not.
SKIP_PLACES = {"Earth", "Solar System", "universe", "outer space", "Milky Way"}

# A protected area is where someone recorded a species, not where it is from.
# Wikidata's "endemic to" is used loosely enough that six widespread birds came
# back endemic to an Indian national park: the common swift and the Eurasian
# eagle-owl to Namdapha, the Eurasian teal and the great hornbill to Kaziranga,
# the great tit to a tiger reserve, the African goliath heron to the
# Sundarbans. None of them is endemic to anything. An island, a basin, a
# desert or a fossil formation is a real origin and is left alone — the royal
# penguin really is Macquarie Island's, dimetrodon really is from the Red Beds
# — so this names the one kind of place that is always a sighting.
PROTECTED = ("National Park", "Nature Reserve", "Tiger Reserve",
             "Wildlife Sanctuary", "Wildlife Refuge", "Game Reserve",
             "Conservation Area", "Biosphere Reserve")


def a_sighting(place):
    return any(w in (place or "") for w in PROTECTED)

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


def check_areas(world):
    """A country named here that world.json does not have would silently
    shade nothing, and a country in two areas would shade twice."""
    have = {c["n"] for c in (world or {}).get("countries") or []}
    seen, bad = {}, []
    for area, members in AREA_COUNTRIES.items():
        if area not in REGION_POINTS:
            bad.append("%s is not a culture area" % area)
        for c in members:
            if have and c not in have:
                bad.append("%s: no country %r in world.json" % (area, c))
            if c in seen:
                bad.append("%s is in both %s and %s" % (c, seen[c], area))
            seen[c] = area
    return bad


def load(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        print("missing %s — skipping" % name, file=sys.stderr)
        return default if default is not None else {}
    with open(path) as fh:
        return json.load(fh)


def main():
    D = load("map_data.json")
    world = load("world.json", {})
    bad = check_areas(world)
    if bad:
        for b in bad:
            print("culture area: %s" % b, file=sys.stderr)
        sys.exit("culture areas do not line up with world.json")
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

    # why a referent has no pin, but only where we turned something down: the
    # card would otherwise tell a reader that nothing says where it is from,
    # which is not the same as "what it said was not evidence"
    refused = {}
    out, counts = {}, {"direct": 0, "hop": 0, "region": 0, "hand": 0}
    for name in sorted(refs):
        hit, kind = None, None
        if name in unplaced_by_hand:
            refused[name] = unplaced_by_hand[name]
            continue              # audited and found to be from nowhere
        for src in (raw, deep):
            if name in src and a_sighting(src[name].get("place")):
                refused.setdefault(
                    name, "its only claim was a sighting in %s, which is where "
                          "it was recorded rather than where it is from"
                          % src[name]["place"])
        if name in placed_by_hand:
            refused.pop(name, None)
            h = placed_by_hand[name]
            hit, kind = {"lat": h["lat"], "lon": h["lon"], "place": h["place"],
                         "placeq": h.get("q"),
                         "via": "placed by hand after checking"}, "hand"
        elif name in raw and raw[name].get("place") not in SKIP_PLACES \
                and not a_sighting(raw[name].get("place")):
            hit, kind = raw[name], "direct"
        elif name in deep and deep[name].get("place") not in SKIP_PLACES \
                and not a_sighting(deep[name].get("place")):
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
    refused = {n: t for n, t in refused.items() if n not in out}
    # only the areas something is actually pinned to; the rest would be a
    # shape with nothing behind it
    drawn = {p[0] for p in places}
    geo = {"places": places, "vias": vias, "refs": out, "why": why,
           "unplaced": refused,
           "areas": {a: c for a, c in AREA_COUNTRIES.items() if a in drawn},
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
    print("%d referents say why they have no pin" % len(refused))
    print("%d culture areas shaded, from %d countries"
          % (len(geo["areas"]), sum(len(c) for c in geo["areas"].values())))
    print("%d places, %d Pokémon reachable" % (len(places), len(species)))
    top = {}
    for name, row in out.items():
        p = places[row[0]][0]
        top[p] = top.get(p, 0) + 1
    for k, n in sorted(top.items(), key=lambda kv: -kv[1])[:12]:
        print("  %-28s %d" % (k, n))


if __name__ == "__main__":
    main()
