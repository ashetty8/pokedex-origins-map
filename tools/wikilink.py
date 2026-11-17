#!/usr/bin/env python3
"""Propose Wikipedia articles for referents that have no link yet.

    python3 -I tools/wikilink.py data/map_data.json            # propose, write nothing
    python3 -I tools/wikilink.py data/map_data.json --apply    # attach the exact matches

Most referent names are the thing itself ("kitsune", "dryad", "trilobite"),
so a batched title lookup resolves them forty at a time — far cheaper than a
search each, which is what `wikisuggest.py` is for and what the leftovers
need.

Two tiers:
  * EXACT — the article's title is the referent's own name, allowing for
    capitalisation, a parenthetical gloss, and a leading "the". Safe to
    attach in bulk; --apply does exactly these.
  * LOOSE — a page exists at some candidate spelling but the title is not the
    name. Printed with its opening words for a person to judge; never applied.

Disambiguation pages are never proposed: sending a reader to a list of
unrelated meanings is worse than no link. Answers are cached, so a run cut
short by rate limiting continues where it stopped.
"""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = "pokedex-origins-map/1.0 (dataset audit; python-urllib)"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wikilink.json")
BATCH = 40


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\([^)]*\)", " ", s)
    s = re.sub(r"^(the|a|an)\s+", "", s.strip(), flags=re.I)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def candidates(name):
    """spellings worth trying as an article title, best first"""
    core = re.sub(r"\s*\([^)]*\)", "", name).replace('"', " ").strip()
    core = re.split(r"\s*/\s*", core)[0].strip()
    out = []
    for t in (core, core.capitalize(), core.title()):
        t = t.strip()
        if t and t not in out: out.append(t)
    # a parenthetical often holds the real term: "kitsune-mochi (fox witch)"
    inner = re.findall(r"\(([^)]+)\)", name)
    for t in inner:
        t = t.strip()
        if len(t.split()) <= 4 and t.capitalize() not in out:
            out.append(t.capitalize())
    return out[:4]


def load_cache():
    try:
        with open(CACHE, encoding="utf-8") as fh: return json.load(fh)
    except Exception:
        return {}


def ask(titles, cache):
    todo = [t for t in titles if t not in cache]
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        q = urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "pageprops|extracts", "exintro": "1", "explaintext": "1",
            "redirects": "1", "titles": "|".join(chunk)})
        req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=40) as fh:
                    data = json.load(fh)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503): raise
                if attempt == 5:
                    with open(CACHE, "w", encoding="utf-8") as fh:
                        json.dump(cache, fh, ensure_ascii=False)
                    sys.stderr.write("rate-limited; %d cached, run again to continue\n" % len(cache))
                    return False
                time.sleep(2 ** attempt)
        back = {}
        for n in data.get("query", {}).get("normalized", []) or []: back[n["to"]] = n["from"]
        for r in data.get("query", {}).get("redirects", []) or []:
            back[r["to"]] = back.get(r["from"], r["from"])
        for p in data["query"]["pages"]:
            asked = back.get(p["title"], p["title"])
            sent = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", p.get("extract", "") or "")).strip()
            cache[asked] = {"title": p["title"], "ok": not p.get("missing"),
                            "dis": "disambiguation" in (p.get("pageprops") or {}),
                            "s": sent[:160]}
        for t in chunk:
            cache.setdefault(t, {"title": t, "ok": False, "dis": False, "s": ""})
        with open(CACHE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
        sys.stderr.write("  checked %d/%d\n" % (min(i + BATCH, len(todo)), len(todo)))
        time.sleep(1.5)
    return True


def main():
    data_path = sys.argv[1]
    apply = "--apply" in sys.argv
    D = json.load(open(data_path, encoding="utf-8"))
    R = D["referents"]
    todo = [r for r in sorted(R) if not R[r].get("w")]
    sys.stderr.write("%d referents without a link\n" % len(todo))
    cache = load_cache()
    titles = []
    for r in todo:
        titles.extend(candidates(r))
    finished = ask(sorted(set(titles)), cache)

    exact, loose, nothing = {}, [], []
    for r in todo:
        hit = None
        for c in candidates(r):
            p = cache.get(c)
            if p and p["ok"] and not p["dis"]:
                hit = p
                break
        if not hit:
            nothing.append(r)
        elif norm(hit["title"]) == norm(r):
            exact[r] = hit["title"]
        else:
            loose.append((r, hit["title"], hit["s"]))

    print("=== exact (%d) — the article is the referent's own name ===" % len(exact))
    for r, t in sorted(exact.items())[:60]:
        print("   %-44s -> %s" % (r[:44], t))
    if len(exact) > 60: print("   … and %d more" % (len(exact) - 60))
    print("\n=== needs a look (%d) — a page exists, under another name ===" % len(loose))
    for r, t, s in sorted(loose)[:40]:
        print("   %-40s -> %-34s %s" % (r[:40], t[:34], s[:52]))
    if len(loose) > 40: print("   … and %d more" % (len(loose) - 40))
    print("\n=== no article at any candidate spelling: %d ===" % len(nothing))
    if not finished:
        print("\n(rate-limited part way; run again to continue)")

    if apply and exact:
        for r, t in exact.items(): R[r]["w"] = t
        with open(data_path, "w", encoding="utf-8") as fh:
            json.dump(D, fh, ensure_ascii=False, indent=0, sort_keys=True)
        print("\nattached %d exact matches to %s" % (len(exact), data_path))


if __name__ == "__main__":
    main()
