#!/usr/bin/env python3
"""Ask Wikidata where each referent comes from.

Every referent in the dataset that names a Wikipedia article gets looked up on
the Wikidata Query Service, which answers a few hundred articles per request —
the per-title REST route is rate-limited into uselessness. For each article we
take the claims that say something geographic, best answer first, and resolve
them to a point.

    python3 -I tools/geofetch.py            # resume; writes data/geo_raw.json

Answers are cached in tools/.geocache.json, so a stopped run continues.
Nothing here touches map_data.json; geo_raw.json sits beside it and
tools/geobuild.py turns it into the file the page loads.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPARQL = "https://query.wikidata.org/sparql"
WP_API = "https://en.wikipedia.org/w/api.php"
UA = "pokedex-origins-map/1.0 (fan dataset; origin geography)"
CACHE = os.path.join(HERE, ".geocache.json")
BATCH = 220

# "Where is this from", best answer first. A coordinate on the thing itself
# beats the country it merely belongs to; an endemic range beats a citizenship.
PROPS = [
    ("P625",  "coordinates"),
    ("P183",  "endemic to"),
    ("P2341", "indigenous to"),
    ("P495",  "country of origin"),
    ("P189",  "found in"),
    ("P1071", "made in"),
    ("P19",   "born in"),
    ("P27",   "citizen of"),
    ("P17",   "country"),
    ("P276",  "located at"),
    ("P131",  "located in"),
]
ORDER = [p for p, _ in PROPS]
WHY = dict(PROPS)

QUERY = """
SELECT ?art ?p ?place ?placeLabel ?coord WHERE {
  VALUES ?art { %s }
  ?art schema:about ?item .
  {
    ?item wdt:P625 ?coord .
    BIND("P625" AS ?p)
  } UNION {
    VALUES (?pp ?p) { %s }
    ?item ?pp ?place .
    OPTIONAL { ?place wdt:P625 ?coord }
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
PAIRS = " ".join('(wdt:%s "%s")' % (p, p) for p in ORDER if p != "P625")


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE) as fh:
            return json.load(fh)
    return {}


def save_cache(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE)


def article_iri(title):
    return "<https://en.wikipedia.org/wiki/%s>" % urllib.parse.quote(
        title.replace(" ", "_"), safe="!$&'()*+,;=:@/~")


def post(url, fields, headers, timeout=120):
    body = urllib.parse.urlencode(fields).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                return json.load(fh)
        except Exception as exc:
            if attempt == 4:
                raise
            wait = 10 + 20 * attempt
            print("  retry in %ds (%s)" % (wait, exc), file=sys.stderr)
            time.sleep(wait)


def point(val):
    m = re.match(r"Point\(([-0-9.eE]+) ([-0-9.eE]+)\)", val or "")
    return (float(m.group(2)), float(m.group(1))) if m else None   # lat, lon


def ask(titles):
    """One SPARQL round: {title: [{p, place, lat, lon}, ...]}."""
    iris = " ".join(article_iri(t) for t in titles)
    data = post(SPARQL, {"query": QUERY % (iris, PAIRS)},
                {"User-Agent": UA, "Accept": "application/sparql-results+json"})
    out = {t: [] for t in titles}
    bytitle = {urllib.parse.quote(t.replace(" ", "_"), safe="!$&'()*+,;=:@/~"): t
               for t in titles}
    for b in data["results"]["bindings"]:
        art = b["art"]["value"].split("/wiki/", 1)[-1]
        title = bytitle.get(art) or urllib.parse.unquote(art).replace("_", " ")
        if title not in out:
            continue
        pt = point((b.get("coord") or {}).get("value"))
        out[title].append({
            "p": b["p"]["value"],
            "place": (b.get("placeLabel") or {}).get("value"),
            "placeq": ((b.get("place") or {}).get("value") or "").split("/")[-1] or None,
            "lat": pt[0] if pt else None,
            "lon": pt[1] if pt else None,
        })
    return out


def resolve_redirects(titles):
    """Titles the query service did not know: follow enwiki redirects once."""
    fixed = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        data = post(WP_API, {"action": "query", "format": "json", "formatversion": "2",
                             "redirects": "1", "titles": "|".join(chunk)},
                    {"User-Agent": UA})
        for r in (data.get("query", {}) or {}).get("redirects", []) or []:
            fixed[r["from"]] = r["to"]
        for n in (data.get("query", {}) or {}).get("normalized", []) or []:
            fixed.setdefault(n["from"], n["to"])
        time.sleep(1.0)
    return fixed


def best(records):
    """The first record, in property order, that resolved to a point."""
    for p in ORDER:
        for r in records:
            if r["p"] == p and r.get("lat") is not None:
                return r
    return None


def main():
    data = json.load(open(os.path.join(ROOT, "data", "map_data.json")))
    refs = data["referents"]
    titles = sorted({v["w"] for v in refs.values() if v.get("w")})
    cache = load_cache()

    def sweep(todo, label):
        print("%s: %d titles" % (label, len(todo)))
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            got = ask(chunk)
            for t in chunk:
                cache[t] = got.get(t, [])
            save_cache(cache)
            print("  %d/%d" % (min(i + BATCH, len(todo)), len(todo)))
            time.sleep(1.0)

    sweep([t for t in titles if t not in cache], "pass 1")

    # Titles with no rows at all are usually redirects, which schema:about
    # does not follow. Ask Wikipedia for the canonical name and sweep those.
    blank = [t for t in titles if not cache.get(t)]
    alias = {}
    if blank:
        print("pass 2: %d titles with no answer — checking for redirects" % len(blank))
        alias = resolve_redirects(blank)
        alias = {k: v for k, v in alias.items() if v != k}
        print("  %d redirect to another title" % len(alias))
        sweep(sorted({v for v in alias.values() if v not in cache}), "pass 2b")

    out, misses = {}, []
    for name, rec in sorted(refs.items()):
        t = rec.get("w")
        if not t:
            continue
        rows = cache.get(t) or cache.get(alias.get(t, ""), [])
        hit = best(rows)
        if hit:
            out[name] = {"lat": round(hit["lat"], 2), "lon": round(hit["lon"], 2),
                         "place": hit["place"] or t, "placeq": hit["placeq"],
                         "via": WHY[hit["p"]]}
        else:
            misses.append(name)

    path = os.path.join(ROOT, "data", "geo_raw.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print("wrote %s" % path)
    print("%d referents placed, %d had a title but no geography, %d have no title"
          % (len(out), len(misses), len(refs) - len(out) - len(misses)))
    byvia = {}
    for v in out.values():
        byvia[v["via"]] = byvia.get(v["via"], 0) + 1
    for k, n in sorted(byvia.items(), key=lambda kv: -kv[1]):
        print("  %-18s %d" % (k, n))


if __name__ == "__main__":
    main()
