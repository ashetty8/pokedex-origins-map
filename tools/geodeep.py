#!/usr/bin/env python3
"""Second geography pass: one hop out from the referent.

geofetch.py asks each referent's own Wikidata item where it is from. Plenty of
things do not say so themselves but sit inside something that does — a kappa is
a yōkai, Zeus is a Greek deity, a kris is a Javanese weapon. This pass follows
one hop (what it is an instance of, part of, or whose culture it belongs to)
and takes the country that thing names.

    python3 -I tools/geodeep.py        # resume; writes data/geo_deep.json

Cached in tools/.geodeep.json. A hop is weaker evidence than a direct claim,
so geobuild.py uses these only where the first pass said nothing.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPARQL = "https://query.wikidata.org/sparql"
UA = "pokedex-origins-map/1.0 (fan dataset; origin geography)"
CACHE = os.path.join(HERE, ".geodeep.json")
BATCH = 120

# The hop, strongest evidence first. "Culture" and "part of" are about
# belonging somewhere; "instance of" and "subclass of" can land on a class so
# broad it says nothing, which is why they come last.
HOPS = [("P2596", "culture"), ("P172", "people"), ("P361", "part of"),
        ("P31", "a kind of"), ("P279", "a kind of")]
# What that hop's target may say about place.
PLACE = [("P495", "from"), ("P17", "in"), ("P2341", "native to"), ("P131", "in")]

# Two ways a hop lies about where something is from, both found by auditing
# what this pass had already placed.
#
# The first is mechanical: a thing that names several places names none of
# them. Zoroastrianism gives seven countries and we were picking whichever
# came back first, which put the Persian huma bird in Canada; "dragon" is
# native to Europe and to Asia, which is how four Japanese dragons, two
# Korean ones and a Slavic one ended up in Europe. Where the parent cannot
# settle on one place, the hop is dropped and the referent falls through to
# the culture area the dataset files it under, which is the better answer in
# every case here.
#
# The second needs a human: some parents name exactly one place and are still
# no evidence, because the class is wider than the place. A loudspeaker is
# "part of" a telephone, invented in the United States; a bell is part of a
# belfry in Belgium; an aircraft catapult is "a kind of" catapult, and so
# from Syracuse by way of Archimedes. King Kong is "a kind of" movie monster
# and movie monsters are from Japan, which is right for Godzilla and absurd
# for an RKO picture. These are the parents too broad to carry a place; a
# culturally bounded one (yōkai, Loong, origami, samurai, Shahnameh) is
# genuinely evidence and is left alone.
BROAD = {
    "designated vegetable",   # a Japanese farm regulation, not where broccoli grew
    "hand fan", "catapult", "telephone", "loudspeaker box", "belfry",
    "movie monster",          # a genre has no country
    "officer candidate", "special agent",
    "creation of the earth",  # the world turtle is told in a dozen places
    "Çakaloğlu Han",          # one caravanserai that happens to contain a fountain
}
# Writing systems are the same failure with a thousand names: refuse "Latin
# script" and the letter falls to the Azerbaijani Latin alphabet, refuse that
# and it lands in Benin. A letter's shape is older than every national
# alphabet that adopted it, so no alphabet places it.
SCRIPTISH = ("script", "alphabet", "abjad", "syllabary")

HOPVALS = " ".join('(wdt:%s "%s")' % (p, p) for p, _ in HOPS)
PLACEVALS = " ".join('(wdt:%s "%s")' % (p, p) for p, _ in PLACE)
HOPRANK = {p: i for i, (p, _) in enumerate(HOPS)}
PLACERANK = {p: i for i, (p, _) in enumerate(PLACE)}
HOPWORD = dict(HOPS)

QUERY = """
SELECT ?art ?hop ?midLabel ?pp ?placeLabel ?coord WHERE {
  VALUES ?art { %s }
  ?art schema:about ?item .
  VALUES (?h ?hop) { %s }
  ?item ?h ?mid .
  VALUES (?p ?pp) { %s }
  ?mid ?p ?place .
  ?place wdt:P625 ?coord .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def load(path, default):
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return default


def save(path, obj):
    with open(path + ".tmp", "w") as fh:
        json.dump(obj, fh)
    os.replace(path + ".tmp", path)


def iri(title):
    return "<https://en.wikipedia.org/wiki/%s>" % urllib.parse.quote(
        title.replace(" ", "_"), safe="!$&'()*+,;=:@/~")


def post(query):
    body = urllib.parse.urlencode({"query": query}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                SPARQL, data=body,
                headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=180) as fh:
                return json.load(fh)
        except Exception as exc:
            if attempt == 4:
                raise
            wait = 10 + 20 * attempt
            print("  retry in %ds (%s)" % (wait, exc), file=sys.stderr)
            time.sleep(wait)


def point(val):
    m = re.match(r"Point\(([-0-9.eE]+) ([-0-9.eE]+)\)", val or "")
    return (float(m.group(2)), float(m.group(1))) if m else None


def main():
    data = json.load(open(os.path.join(ROOT, "data", "map_data.json")))
    refs = data["referents"]
    first = load(os.path.join(ROOT, "data", "geo_raw.json"), {})
    # Only what the first pass could not place, and only referents whose
    # category could plausibly belong somewhere. A concept has no homeland.
    kinds = {"mythology", "folklore", "object", "person", "media & art", "food",
             "earth & sky", "life", "prehistoric"}
    titles = sorted({r["w"] for n, r in refs.items()
                     if r.get("w") and n not in first and r.get("k") in kinds})
    cache = load(CACHE, {})
    todo = [t for t in titles if t not in cache]
    print("%d unplaced titles, %d to ask" % (len(titles), len(todo)))

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        res = post(QUERY % (" ".join(iri(t) for t in chunk), HOPVALS, PLACEVALS))
        got = {t: [] for t in chunk}
        back = {urllib.parse.quote(t.replace(" ", "_"), safe="!$&'()*+,;=:@/~"): t
                for t in chunk}
        for b in res["results"]["bindings"]:
            art = b["art"]["value"].split("/wiki/", 1)[-1]
            t = back.get(art) or urllib.parse.unquote(art).replace("_", " ")
            if t not in got:
                continue
            pt = point((b.get("coord") or {}).get("value"))
            if not pt:
                continue
            got[t].append({"hop": b["hop"]["value"], "via": b["pp"]["value"],
                           "mid": (b.get("midLabel") or {}).get("value"),
                           "place": (b.get("placeLabel") or {}).get("value"),
                           "lat": pt[0], "lon": pt[1]})
        cache.update(got)
        save(CACHE, cache)
        print("  %d/%d" % (min(i + BATCH, len(todo)), len(todo)))
        time.sleep(1.0)

    out, dropped = {}, 0
    for name, rec in sorted(refs.items()):
        t = rec.get("w")
        if not t or name in first:
            continue
        rows = cache.get(t) or []
        if not rows:
            continue
        rows = [r for r in rows if (r["mid"] or "") not in BROAD
                and not any(w in (r["mid"] or "").lower() for w in SCRIPTISH)]
        # a parent that gives two different answers through the same property
        # has no single place to lend
        split = set()
        for r in rows:
            for other in rows:
                if r["mid"] == other["mid"] and r["via"] == other["via"] \
                        and r["place"] != other["place"]:
                    split.add(r["mid"])
        rows = [r for r in rows if r["mid"] not in split]
        if not rows:
            dropped += 1
            continue
        rows.sort(key=lambda r: (HOPRANK.get(r["hop"], 9), PLACERANK.get(r["via"], 9)))
        r = rows[0]
        out[name] = {"lat": round(r["lat"], 2), "lon": round(r["lon"], 2),
                     "place": r["place"], "via": HOPWORD.get(r["hop"], "via") + " " +
                     (r["mid"] or "?"), "hop": 1}

    path = os.path.join(ROOT, "data", "geo_deep.json")
    save(path, out)
    print("wrote %s: %d more referents placed, %d hops refused as no evidence"
          % (path, len(out), dropped))
    byplace = {}
    for v in out.values():
        byplace[v["place"]] = byplace.get(v["place"], 0) + 1
    for k, n in sorted(byplace.items(), key=lambda kv: -kv[1])[:15]:
        print("  %-28s %d" % (k, n))


if __name__ == "__main__":
    main()
