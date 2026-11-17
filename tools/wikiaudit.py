#!/usr/bin/env python3
"""Check referents against the Wikipedia pages they claim.

Reads data/map_data.json, asks Wikipedia for the first paragraph of every
title it names, and reports three things:
  * titles that do not resolve (gone, renamed, or never existed)
  * titles that land on a disambiguation page (the link is not actually about
    the referent)
  * first sentences whose wording contradicts the category the referent carries

The last one only speaks when the wording is unambiguous — "is an extinct
genus of", "is a species of", "in Greek mythology" — so the output stays
short enough to read by hand. It never edits anything.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = "pokedex-origins-map/1.0 (dataset audit; python-urllib)"
BATCH = 40

# first-sentence wording -> the category it implies, with the phrase that said so
RULES = [
    ("prehistoric", r"\b(is|was) an? (extinct|prehistoric)\b|\bextinct (genus|species|family|order|group)\b|\blived during the\b.*\b(period|epoch)\b"),
    ("life",        r"\bis a (species|genus|family|subspecies|breed|cultivar) of\b|\bis a (small |large |marine |freshwater |flowering |deciduous |evergreen )*(bird|fish|mammal|reptile|amphibian|insect|arachnid|crustacean|mollusc|mollusk|plant|tree|shrub|flower|herb|fungus|alga|beetle|moth|butterfly|snake|lizard|frog|spider)\b"),
    ("mythology",   r"\bin (greek|roman|norse|egyptian|hindu|japanese|chinese|aztec|mayan|slavic|celtic|mesopotamian|sumerian|babylonian|polynesian|hawaiian) mytholog|\bis a (god|goddess|deity|titan)\b|\bis the (god|goddess) of\b"),
    ("folklore",    r"\bis a legendary creature\b|\bin folklore\b|\bfolkloric\b|\by[ōo]kai\b|\bis a cryptid\b|\bfairy tale\b"),
    ("food",        r"\bis a (dish|food|dessert|bread|cake|pastry|soup|stew|noodle|candy|confection|sweet|beverage|drink)\b|\bis a traditional .{0,30}(dish|dessert|sweet|bread)\b"),
    ("object",      r"\bis a (tool|weapon|device|machine|instrument|garment|vehicle|utensil|container|firearm|sword|blade|helmet|armou?r)\b|\bis a type of (tool|weapon|garment|vehicle|hat|shoe)\b"),
    ("earth & sky", r"\bis a (mineral|rock|gemstone|star|constellation|planet|cloud|crater|volcano|mountain|river|lake|glacier)\b|\bis a weather phenomenon\b|\bis an? (atmospheric|astronomical|geological) \w+\b"),
    ("person",      r"\bwas an? [a-z ]{0,30}(emperor|empress|king|queen|shogun|samurai|politician|actor|actress|singer|boxer|wrestler|painter|writer|poet|monk|general|explorer)\b|\(born \d{4}\)"),
]


def first_sentence(text):
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"\([^)]*\)", "", t)                     # drop parenthetical glosses
    m = re.match(r"(.{20,400}?\.)(?: [A-Z]|$)", t)
    return (m.group(1) if m else t[:260]).strip()


def implied(sentence):
    low = sentence.lower()
    for kind, pattern in RULES:
        m = re.search(pattern, low)
        if m:
            return kind, m.group(0)[:46]
    return None, None


CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wikicache.json")


def load_cache():
    try:
        with open(CACHE, encoding="utf-8") as fh: return json.load(fh)
    except Exception:
        return {}


def save_cache(c):
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(c, fh, ensure_ascii=False)


def fetch(titles):
    # Wikipedia rate-limits a long sweep, so answers are cached on disk and a
    # later run picks up where this one stopped instead of starting over.
    out = load_cache()
    titles = [t for t in titles if t not in out]
    if not titles:
        sys.stderr.write("  every title already cached\n")
        return out
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        q = urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "extracts|pageprops", "exintro": "1", "explaintext": "1",
            "redirects": "1", "titles": "|".join(chunk),
        })
        req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
        # Wikipedia throttles bursts: back off and retry rather than giving up
        # halfway through an audit.
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=40) as fh:
                    data = json.load(fh)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503):
                    raise
                if attempt == 5:
                    save_cache(out)
                    sys.stderr.write("  still rate-limited; %d titles cached, "
                                     "run again later to continue\n" % len(out))
                    return out
                wait = 2 ** attempt
                sys.stderr.write("  %s — waiting %ds\n" % (e.code, wait))
                time.sleep(wait)
        norm = {}
        for n in data.get("query", {}).get("normalized", []) or []:
            norm[n["to"]] = n["from"]
        for r in data.get("query", {}).get("redirects", []) or []:
            norm[r["to"]] = norm.get(r["from"], r["from"])
        for page in data.get("query", {}).get("pages", []):
            title = page.get("title")
            asked = norm.get(title, title)
            out[asked] = {
                "title": title,
                "missing": page.get("missing", False),
                "disambig": "disambiguation" in (page.get("pageprops") or {}),
                "extract": page.get("extract", ""),
            }
        sys.stderr.write("  fetched %d/%d\n" % (min(i + BATCH, len(titles)), len(titles)))
        save_cache(out)
        time.sleep(2.0)
    return out


def main():
    data_path = sys.argv[1]
    only_inferred = "--all" not in sys.argv
    D = json.load(open(data_path, encoding="utf-8"))
    R = D["referents"]
    picked = {r: v for r, v in R.items()
              if v.get("w") and (v.get("i") or not only_inferred)}
    titles = sorted({v["w"] for v in picked.values()})
    sys.stderr.write("asking Wikipedia about %d titles for %d referents\n" % (len(titles), len(picked)))
    pages = fetch(titles)

    missing, disambig, mismatch = [], [], []
    for r, v in sorted(picked.items()):
        page = pages.get(v["w"])
        if not page:
            missing.append((r, v["w"], "no answer"))
            continue
        if page["missing"]:
            missing.append((r, v["w"], "no such page"))
            continue
        if page["disambig"]:
            disambig.append((r, v["w"]))
            continue
        sent = first_sentence(page["extract"])
        kind, why = implied(sent)
        if kind and kind != v.get("k"):
            mismatch.append((len(v["s"]), r, v.get("k"), kind, why, sent[:150]))

    print("\n=== titles that do not resolve (%d) ===" % len(missing))
    for r, w, why in missing:
        print("   %-40s -> %-40s %s" % (r[:40], w[:40], why))
    print("\n=== titles landing on a disambiguation page (%d) ===" % len(disambig))
    for r, w in disambig:
        print("   %-40s -> %s" % (r[:40], w))
    print("\n=== wording contradicts the category (%d) ===" % len(mismatch))
    for n, r, had, want, why, sent in sorted(mismatch, reverse=True):
        print("   %-36s %-12s -> %-12s (%d Pokémon)  [%s]" % (r[:36], had, want, n, why))
        print("        %s" % sent)


if __name__ == "__main__":
    main()
