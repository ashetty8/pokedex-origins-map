#!/usr/bin/env python3
"""Suggest a Wikipedia article for referents that have no link yet.

    python3 -I tools/wikisuggest.py data/map_data.json [--kind folklore] [--limit 100]

Many referent names are descriptive phrases Bulbapedia wrote ("black cat
superstition", "dwarf blacksmith"), not article titles, so a direct title
lookup misses them. This searches instead and prints the top candidate for
each with the opening words of the article, for a person to accept or reject.

It writes nothing. Pipe the output into a review, then apply with
`flagkit.py set-wiki`. Results are cached so a rate-limited run resumes.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = "pokedex-origins-map/1.0 (dataset audit; python-urllib)"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wikisearch.json")


def load_cache():
    try:
        with open(CACHE, encoding="utf-8") as fh: return json.load(fh)
    except Exception:
        return {}


def ask(query, cache):
    if query in cache:
        return cache[query]
    q = urllib.parse.urlencode({"action": "query", "format": "json", "formatversion": "2",
                                "list": "search", "srsearch": query, "srlimit": "3"})
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=40) as fh:
                data = json.load(fh)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503):
                raise
            time.sleep(2 ** attempt)
    else:
        return None
    hits = [{"title": h["title"],
             "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", ""))}
            for h in data.get("query", {}).get("search", [])]
    cache[query] = hits
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)
    return hits


def clean(name):
    """The searchable core of a referent name. These are phrases Bulbapedia
       wrote, so the article is usually behind the leading term: "bakeneko and
       lamp oil" is about the bakeneko, "black dog of folklore" the black dog.
       Searching the whole phrase finds compilation albums and video games."""
    t = re.sub(r"\s*\([^)]*\)", " ", name).strip().strip('"')
    t = re.split(r"\s+and\s+|\s*/\s*", t)[0]
    t = re.sub(r"\s+of\s+(folklore|legend|myth|lore)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\b(superstition|lore)\b\s*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip() or name


def main():
    data_path = sys.argv[1]
    kind = None
    if "--kind" in sys.argv:
        kind = sys.argv[sys.argv.index("--kind") + 1]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 200
    D = json.load(open(data_path, encoding="utf-8"))
    R, G, F = D["referents"], D["groups"], D["families"]

    def top_family(r):
        g = G.get(R[r].get("g") or "", {})
        seen = set()
        while g.get("p") and g["p"] not in seen:
            seen.add(g["p"]); g = G[g["p"]]
        return g.get("f")

    todo = [r for r in sorted(R) if not R[r].get("w")]
    if kind:
        todo = [r for r in todo if (F.get(top_family(r) or "", {}) or {}).get("k") == kind]
    todo = todo[:limit]
    sys.stderr.write("searching for %d referents without a link\n" % len(todo))
    cache = load_cache()
    for i, r in enumerate(todo):
        hits = ask(clean(r), cache)
        if hits is None:
            sys.stderr.write("rate-limited after %d; run again to continue\n" % i)
            break
        if not hits:
            print("%-46s (nothing found)" % r[:46]); continue
        best = hits[0]
        print("%-46s -> %-34s %s" % (r[:46], best["title"][:34], best["snippet"][:60]))
        for alt in hits[1:]:
            print("%-46s    also: %s" % ("", alt["title"][:40]))
        time.sleep(1.2)


if __name__ == "__main__":
    main()
