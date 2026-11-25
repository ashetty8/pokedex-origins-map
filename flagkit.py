#!/usr/bin/env python3
"""flagkit — inspect and patch the Pokedex Origins Map dataset without burning tokens.

Everything here runs locally against work/map_data.json. Print small, print facts.

Files: data/map_data.json is the source of truth, one key per line so diffs read;
dist/map_data.json is the minified copy the page fetches, rewritten on every save.

  python3 flagkit.py show <name>...        what the data says about a referent/group/family/species
  python3 flagkit.py grep <text>           referents, groups and families whose name matches
  python3 flagkit.py species <name>        every Pokemon under a referent or cluster (with sprite forms)
  python3 flagkit.py where <pokemon>       which referents/clusters a Pokemon hangs off
  python3 flagkit.py check                 integrity pass (parents, children, family lists, counts)

  python3 flagkit.py patch apply <file>    replay this structure onto a freshly generated dataset
  python3 flagkit.py rebased               after a replay: record the build these corrections now sit on
  python3 flagkit.py build                 rewrite dist/map_data.json (the minified published copy)
  python3 flagkit.py build --bust          and stamp each asset URL with its content hash (the site)

  python3 flagkit.py published             is the live artifact what this tree last sent?
  python3 flagkit.py published seen <id>   the version id the artifact's file listing reports
  python3 flagkit.py published stamp <id>  after our own publish: the two are in step again
  python3 flagkit.py published adopt <dir> take live app files we did not write into app/

  python3 flagkit.py move-family <group> <family>      refile a cluster, recount both families
  python3 flagkit.py nest <child> <parent>             make <child> a child cluster of <parent>
  python3 flagkit.py unnest <child>                    move a cluster back up to its family
  python3 flagkit.py merge <from-group> <into-group>   fold one cluster's referents into another
  python3 flagkit.py regroup <new> <parent> <child>... gather clusters under a new one (<parent> may be a family)
  python3 flagkit.py rename <old> <new>                rename a cluster and every reference to it
  python3 flagkit.py split-family <old> <new> <cluster>...  move top-level clusters into a new family
  python3 flagkit.py rename-family <old> <new>         rename a family everywhere
  python3 flagkit.py merge-ref <from> <into>           fold one referent into another
  python3 flagkit.py split-cluster <src> <new> <ref>... move some referents into a new sibling
  python3 flagkit.py move-ref <referent> <cluster>     move a referent into another cluster
  python3 flagkit.py add-ref <new> <cluster> <id>...   a referent the build missed, on those Pokemon
  python3 flagkit.py split-ref <src> <new> [id]...    break a compound referent in two (<src> keeps its own name)
  python3 flagkit.py rename-ref <old> <new>           rename a referent everywhere it is named
  python3 flagkit.py set-allusion <referent> on|off   a nod to, rather than drawn from
  python3 flagkit.py set-meta <referent> on|off      from inside the franchise, not from the world
  python3 flagkit.py set-wiki <referent> [title]       set or clear a referent's Wikipedia title ("Page#Section" allowed)
  python3 flagkit.py set-url <referent> [url]          a source that is no Wikipedia article (Wiktionary, say)
  python3 flagkit.py set-region <cluster> <family> <region>   refile a cluster by where it is from
  python3 flagkit.py set-kind <group|referent> <kind>  change a category
  python3 flagkit.py normalize-case                    one spelling per referent, from its source text
  python3 flagkit.py recount                           recompute every family n and cluster tn

Write commands print a one-line diff summary, re-run `check`, and refuse to save
if the check fails. Pass --dry to see the summary without saving.
"""
import datetime, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "map_data.json")      # readable, one key per line
DIST = os.path.join(HERE, "dist", "map_data.json")      # minified, what gets published
STAMP = os.path.join(HERE, "data", "applied_build.json")
PUB = os.path.join(HERE, "data", "published.json")
PUBLISHED_FILES = ("index.html", "style.css", "app.js",
                   "map_data.json", "world.json", "geo.json",
                   "sprites.json", "form_sprites.json")


# ---------- the one hazard the data cannot describe ----------
# Corrections live in map_data.json itself — that is the point of dropping the
# overlay, and it is right. The cost is that the single thing which can quietly
# undo them is a fresh generator build dropped over the top: the file still
# parses, still passes every integrity check, and is simply missing the work.
#
# Nothing inside the dataset can catch that, because the evidence leaves with
# the file. So the build the corrections were made on is recorded beside it,
# and every command that could publish or extend the work checks the two still
# agree. The alternative is remembering, which is what a warning repeated in
# every correction note was standing in for.

def stamp_read():
    try:
        with open(STAMP, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def stamp_write(D):
    rec = {"build": (D.get("meta") or {}).get("build"),
           "updated": datetime.datetime.now(datetime.timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(STAMP, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return rec


def guard_build(D):
    """None when the dataset is the one the corrections were made on, else the
       reason it is not — returned rather than printed, so callers decide."""
    rec = stamp_read()
    if not rec or not rec.get("build"):
        return None                      # nothing recorded yet; nothing to lose
    now = (D.get("meta") or {}).get("build")
    if now == rec["build"]:
        return None
    return ("STOP — data/map_data.json says build %s, but the corrections here were\n"
            "made on %s (recorded %s). A fresh build has replaced the corrected\n"
            "file and the edits are not in it. Replay them before anything else:\n"
            "    python3 -I flagkit.py patch apply <the fresh map_data.json>\n"
            "put the resulting .patched.json at data/map_data.json, then:\n"
            "    python3 -I flagkit.py rebased"
            % (now or "no build", rec["build"], rec.get("updated", "?")))


# ---------- the second hazard: the artifact is ahead of app/ ----------
# CLAUDE.md says data/ and app/ ARE the published version. Nothing made that
# true. Another session can publish a fix straight from its own tree and never
# commit it, and this tree goes on believing its app/ is current: `build`
# assembles dist/ from whatever app/ holds, a publish only guards the files you
# actually send, and so the other session's work goes back out reverted — no
# refusal, no conflict, no diff to read. It happened on 2026-11-23; three fixes
# lived only in the artifact and were caught by comparing byte counts by eye.
#
# The build stamp above can check itself, because the build id is inside the
# file. This one cannot: the evidence is the version id the artifact reports,
# which lives outside the repo. So it is carried in by hand — one cheap file
# listing, then `published seen <id>` — and what the guard buys is that
# forgetting to look is no longer silent. `published stamp <id>` after our own
# publish says the two are in step again.

def pub_read():
    try:
        with open(PUB, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def pub_save(rec):
    with open(PUB, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return rec


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pub_hashes(root):
    """sha256 of every published file under root, in the same form the
       artifact's own file listing prints — so the two can be compared path by
       path instead of by size, which is how the near-miss was nearly missed."""
    import hashlib
    out = {}
    for name in PUBLISHED_FILES:
        p = os.path.join(root, name)
        if not os.path.exists(p):
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        out[name] = h.hexdigest()
    return out


def guard_published():
    """None when the live artifact is the version this tree last sent, else the
       reason it is not — returned rather than printed, as guard_build does."""
    rec = pub_read()
    if not rec:
        return None                      # never stamped; nothing to compare
    ours = (rec.get("ours") or {}).get("version")
    live = (rec.get("live") or {}).get("version")
    if not ours or not live or ours == live:
        return None
    return ("STOP — the artifact is live at %s (seen %s), but the last version\n"
            "this tree published was %s. Someone published from another tree, so\n"
            "app/ may be missing their work, and a build from here would revert\n"
            "it with nothing to read. Fetch the live files and reconcile:\n"
            "    Artifact read paths=[\"app.js\",\"style.css\",\"index.html\"] out_dir=<dir>\n"
            "    python3 -I flagkit.py published adopt <dir>"
            % (live, (rec.get("live") or {}).get("seen", "?"), ours))


def published_adopt(rec, src):
    """Take the live app files into app/. It names the files it left alone as
       well as the ones it took, because 'nothing changed' is the answer that
       most needs saying out loud here."""
    import filecmp, shutil
    if not os.path.isdir(src):
        sys.exit("%s is not a directory" % src)
    took, same, missing = [], [], []
    for name in ("index.html", "style.css", "app.js"):
        s, d = os.path.join(src, name), os.path.join(HERE, "app", name)
        if not os.path.exists(s):
            missing.append(name)
        elif os.path.exists(d) and filecmp.cmp(s, d, shallow=False):
            same.append(name)
        else:
            shutil.copy2(s, d)
            took.append(name)
    for n in took:
        print("  adopted   app/%s" % n)
    for n in same:
        print("  unchanged app/%s" % n)
    for n in missing:
        print("  not in %s: %s" % (src, n))
    live = (rec.get("live") or {}).get("version")
    if live:
        # the hashes recorded at stamp time describe dist/, which has not been
        # rebuilt yet — claiming them here would be claiming a publish we did
        # not make
        rec["ours"] = {"version": live, "at": now_utc(), "files": {}}
        pub_save(rec)
        print("recorded: app/ now holds version %s" % live)
    if took:
        print("Read the diff before you build — `git diff app/`. This is somebody\n"
              "else's work arriving, and the commit for it should say so.")
    return 0


def published_cmd(rest):
    rec = pub_read() or {}
    sub = (rest[:1] or ["status"])[0]
    if sub == "status":
        ours, live = rec.get("ours") or {}, rec.get("live") or {}
        if not ours and not live:
            return print("nothing recorded yet — run `published stamp <version-id>`\n"
                         "after the next publish and the guard starts working")
        print("ours: %s (%s)" % (ours.get("version") or "—", ours.get("at", "?")))
        print("live: %s (seen %s)" % (live.get("version") or "—", live.get("seen", "?")))
        stop = guard_published()
        print(stop if stop else "in step — the live artifact is what this tree last sent")
        return sys.exit(1 if stop else 0)
    if sub == "stamp":
        if len(rest) < 2:
            sys.exit("published stamp <version-id>   (the id the publish returned)")
        rec["ours"] = {"version": rest[1], "at": now_utc(),
                       "files": pub_hashes(os.path.dirname(DIST))}
        rec["live"] = {"version": rest[1], "seen": now_utc()}
        pub_save(rec)
        return print("recorded: the live artifact is version %s, sent from this tree "
                     "(%d files hashed)" % (rest[1], len(rec["ours"]["files"])))
    if sub == "seen":
        if len(rest) < 2:
            sys.exit("published seen <version-id>   (from the artifact's file listing)")
        rec.setdefault("ours", {})
        rec["live"] = {"version": rest[1], "seen": now_utc()}
        pub_save(rec)
        stop = guard_published()
        print(stop if stop else "in step — the live artifact is what this tree last sent")
        return sys.exit(1 if stop else 0)
    if sub == "adopt":
        if len(rest) < 2:
            sys.exit("published adopt <dir holding the files fetched from the artifact>")
        return published_adopt(rec, rest[1])
    sys.exit("published [status | stamp <id> | seen <id> | adopt <dir>]")


def load():
    if not os.path.exists(DATA):
        sys.exit("no work/map_data.json — fetch it first (Artifact read, path map_data.json, out_dir work/)")
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def meta_counts(D):
    """What the four numbers in the page's header mean, in one place.

       A cluster is a node holding more than one referent — the same test the
       page uses for "clusters only" and for its every-cluster list. The rest
       are plain lengths."""
    return {"species":   len(D["species"]),
            "referents": len(D["referents"]),
            "families":  len(D["families"]),
            "groups":    len(D["groups"]),
            "clusters":  sum(1 for v in D["groups"].values()
                             if len(v.get("m") or []) > 1)}


def remeta(D):
    """meta came from a generator that is no longer here, and nothing updated
       it afterwards: every merge left meta.clusters a little further from the
       truth, and the header was printing 574 where 569 clusters existed. So
       the counts are derived here, on the way out, and no command has to
       remember to."""
    D.setdefault("meta", {}).update(meta_counts(D))


def save(D):
    remeta(D)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False, indent=0, sort_keys=True)
    stamp_write(D)
    build(D)


def short_hash(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


def cache_bust(dist):
    """Put each asset's own content hash in the URL that asks for it.

       GitHub Pages serves everything with max-age=600 and no way to change it,
       and each file's ten minutes runs on its own clock. So a browser that has
       been here before can pair a fresh index.html with a stale app.js, or —
       the one that matters for this project, where most changes are data — a
       current app.js with yesterday's geo.json. That is not a slow update, it
       is a build that never existed, and it is what you get today.

       A hash in the query makes a changed file a different URL, so it is
       fetched rather than remembered, and an unchanged one keeps its cache.
       The HTML itself still takes up to ten minutes to turn over; what this
       buys is that when it does, everything it names turns over with it.

       Only the static site needs this. The artifact serves a version at a
       time and replaces the lot, so its build is left alone."""
    stamped = {}
    # app.js asks for these itself, so they are rewritten there — and app.js
    # has to be hashed after that, or its own stamp would describe a file that
    # no longer exists
    with open(os.path.join(dist, "app.js"), encoding="utf-8") as f:
        js = f.read()
    for name in ("sprites.json", "form_sprites.json", "map_data.json",
                 "geo.json", "world.json"):
        p = os.path.join(dist, name)
        if not os.path.exists(p):
            continue
        needle = 'fetch("%s")' % name
        if js.count(needle) != 1:
            sys.exit("cache_bust: expected one fetch(%r) in app.js, found %d"
                     % (name, js.count(needle)))
        h = short_hash(p)
        js = js.replace(needle, 'fetch("%s?v=%s")' % (name, h))
        stamped[name] = h
    with open(os.path.join(dist, "app.js"), "w", encoding="utf-8") as f:
        f.write(js)

    # index.html asks for these two
    with open(os.path.join(dist, "index.html"), encoding="utf-8") as f:
        html = f.read()
    for name, needle in (("style.css", 'href="style.css"'),
                         ("app.js", 'src="app.js"')):
        p = os.path.join(dist, name)
        if html.count(needle) != 1:
            sys.exit("cache_bust: expected one %s in index.html, found %d"
                     % (needle, html.count(needle)))
        h = short_hash(p)
        html = html.replace(needle, needle[:-1] + "?v=" + h + '"')
        stamped[name] = h
    with open(os.path.join(dist, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return stamped


def build(D, bust=False):
    """Assemble dist/: the minified dataset plus the three app files, which is
       exactly what gets published and what a local preview serves."""
    import shutil
    dist = os.path.dirname(DIST)
    os.makedirs(dist, exist_ok=True)
    with open(DIST, "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False, separators=(",", ":"))
    for name in ("index.html", "style.css", "app.js"):
        src = os.path.join(HERE, "app", name)
        if os.path.exists(src): shutil.copy2(src, os.path.join(dist, name))
    # The atlas layer: pre-projected land outlines and the geography of each
    # referent. Both are generated (tools/worldgen.py, tools/geobuild.py) and
    # already minified, so they are copied rather than re-dumped.
    extra = []
    # sprites.json and form_sprites.json used to live in the artifact only,
    # which was fine while the artifact was the only place the page ran. A
    # static host has no such store, so they are in data/ now and copied like
    # any other generated asset.
    for name in ("world.json", "geo.json", "sprites.json", "form_sprites.json"):
        src = os.path.join(HERE, "data", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dist, name))
            extra.append(name)
    note = ""
    if bust:
        note = " · %d assets stamped with their content hash" % len(cache_bust(dist))
    return "built %s: map_data.json (%d KB) + index.html, style.css, app.js%s%s" % (
        dist, os.path.getsize(DIST) // 1024,
        (" + " + ", ".join(extra)) if extra else "", note)


# ---------- reading ----------

def fam_species(D, fam):
    s = set()
    for g, v in D["groups"].items():
        if v.get("f") == fam:
            for m in v.get("m") or []:
                r = D["referents"].get(m)
                if r:
                    s |= set(r["s"])
    return s


def sub_species(D, g, seen=None):
    seen = seen or set()
    if g in seen:
        return set()
    seen.add(g)
    gg = D["groups"].get(g) or {}
    s = set()
    for m in gg.get("m") or []:
        r = D["referents"].get(m)
        if r:
            s |= set(r["s"])
    for c in gg.get("ch") or []:
        s |= sub_species(D, c, seen)
    return s


def name_of(D, i):
    sp = D["species"].get(str(i))
    return "#%04d %s" % (int(i), sp[0]) if sp else "#%s ?" % i


def parent_of(D, g):
    return (D["groups"].get(g) or {}).get("p")


def show(D, name):
    G, R, F = D["groups"], D["referents"], D["families"]
    key = name.lower()
    hit = False
    if key in R:
        r = R[key]
        hit = True
        print("REFERENT %r  cluster=%s kind=%s%s%s" % (
            name, r.get("g"), r.get("k"), " wiki=" + r["w"] if r.get("w") else "",
            " INFERRED" if r.get("i") else ""))
        print("  %d Pokemon: %s" % (len(r["s"]), ", ".join(name_of(D, i) for i in r["s"])))
        forms = (D.get("formrefs") or {}).get(key) or {}
        if forms:
            print("  form overrides: %s" % json.dumps(forms))
    if name in G:
        g = G[name]
        hit = True
        print("CLUSTER %r  family=%s kind=%s%s%s" % (
            name, g.get("f"), g.get("k"), " parent=" + g["p"] if g.get("p") else "",
            " LEAF" if g.get("leaf") else ""))
        print("  own referents (%d): %s" % (len(g.get("m") or []), ", ".join(g.get("m") or [])))
        print("  children (%d): %s" % (len(g.get("ch") or []), ", ".join(g.get("ch") or [])))
        print("  n=%s tn=%s  subtree Pokemon=%d" % (g.get("n"), g.get("tn"), len(sub_species(D, name))))
    if name in F:
        f = F[name]
        hit = True
        kids = [g for g, v in G.items() if v.get("f") == name]
        print("FAMILY %r  kind=%s branch=%s n=%s (computed %d)" % (
            name, f.get("k"), f.get("b"), f.get("n"), len(fam_species(D, name))))
        print("  clusters c=%s" % (f.get("c") or []))
        print("  leaves   l=%s" % (f.get("l") or []))
        print("  %d groups filed here in total" % len(kids))
    if not hit:
        print("no referent, cluster or family called %r — try: grep" % name)


def grep(D, text):
    t = text.lower()
    for label, keys in (("referent", D["referents"]), ("cluster", D["groups"]), ("family", D["families"])):
        hits = sorted(k for k in keys if t in k.lower())
        if hits:
            print("%s (%d): %s" % (label, len(hits), ", ".join(hits[:40]) + (" …" if len(hits) > 40 else "")))


def species_cmd(D, name):
    key = name.lower()
    if key in D["referents"]:
        ids = D["referents"][key]["s"]
    elif name in D["groups"]:
        ids = sorted(sub_species(D, name))
    else:
        return print("unknown %r" % name)
    forms = (D.get("formrefs") or {}).get(key) or {}
    for i in ids:
        slug = forms.get(str(i))
        print("  %s%s" % (name_of(D, i), "   [form: %s]" % slug if slug else ""))


def where(D, poke):
    want = poke.lower()
    ids = [i for i, s in D["species"].items() if s[0].lower() == want]
    if not ids:
        return print("no Pokemon called %r" % poke)
    for i in ids:
        print(name_of(D, i))
        for rk, r in sorted(D["referents"].items()):
            if int(i) in r["s"]:
                chain, g = [], r.get("g")
                while g:
                    chain.append(g)
                    g = parent_of(D, g)
                print("  %-34s cluster path: %s" % (rk, " < ".join(chain) or "—"))


def check(D, quiet=False):
    G, F = D["groups"], D["families"]
    bad, parent = [], {}
    for g, v in G.items():
        for c in v.get("ch") or []:
            if c not in G:
                bad.append(("missing child", g, c))
            elif c in parent:
                bad.append(("two parents", c, parent[c], g))
            else:
                parent[c] = g
    for g, v in G.items():
        p = v.get("p")
        if p and parent.get(g) != p:
            bad.append(("p disagrees with ch", g, p, parent.get(g)))
        if not p and parent.get(g):
            bad.append(("missing p", g, parent.get(g)))
        if bool(v.get("leaf")) != (len(v.get("m") or []) <= 1):
            bad.append(("leaf flag disagrees with referent count", g))
        want = len(sub_species(D, g))
        if v.get("tn") is not None and v["tn"] != want:
            bad.append(("stale tn", g, v["tn"], want))
        own = len({i for m in (v.get("m") or []) if m in D["referents"]
                   for i in D["referents"][m]["s"]})
        if v.get("n") != own:
            bad.append(("stale n (own referents)", g, v.get("n"), own))
    for fam, f in F.items():
        for g in (f.get("c") or []) + (f.get("l") or []):
            if g not in G:
                bad.append(("missing group", fam, g))
            elif G[g].get("f") != fam:
                bad.append(("f mismatch", fam, g, G[g].get("f")))
        want = len(fam_species(D, fam))
        if f.get("n") != want:
            bad.append(("stale family n", fam, f.get("n"), want))
    for fam, f in F.items():
        for region, lst in (f.get("rg") or {}).items():
            for g in lst:
                if g not in G:
                    bad.append(("region names a missing cluster", fam, region, g))
                elif G[g].get("f") != fam:
                    bad.append(("region holds a cluster of another family", fam, region, g))
        if f.get("rg"):
            placed = {g for lst in f["rg"].values() for g in lst}
            top = set((f.get("c") or []) + (f.get("l") or []))
            for g in sorted(top - placed):
                bad.append(("cluster in no region", fam, g))
    for r, v in D["referents"].items():
        w = v.get("w")
        if w and ("#" in w or w.lower().startswith(("http://", "https://"))):
            bad.append(("w is not a bare article title", r, w))
        if v.get("ws") and not w:
            bad.append(("section with no article", r, v["ws"]))
        if v.get("u") and w:
            bad.append(("both an article and a stand-in link", r, w, v["u"]))
    for g, v in G.items():
        fam = v.get("f")
        if fam and not v.get("p"):
            if g not in (F[fam].get("c") or []) + (F[fam].get("l") or []):
                bad.append(("top cluster not listed by its family", fam, g))
    # the header's own numbers. A fresh dataset can arrive with these already
    # wrong, and they are the first thing a reader sees.
    for k, want in sorted(meta_counts(D).items()):
        if D.get("meta", {}).get(k) != want:
            bad.append(("stale meta." + k, D.get("meta", {}).get(k), want))
    if not quiet:
        print("integrity: %s" % ("clean" if not bad else "%d problems" % len(bad)))
        for b in bad[:30]:
            print("  ", b)
    return bad


# ---------- writing ----------

def recount(D):
    for fam in D["families"]:
        D["families"][fam]["n"] = len(fam_species(D, fam))
    for g, v in D["groups"].items():
        if v.get("tn") is not None or (v.get("ch") or []):
            v["tn"] = len(sub_species(D, g))
        v["n"] = len({i for m in (v.get("m") or []) if m in D["referents"]
                      for i in D["referents"][m]["s"]})
    remeta(D)          # a write that makes or folds a cluster moves the header too
    return "recounted %d families and every cluster total" % len(D["families"])


def fam_list_for(D, g):
    """clusters with several referents live in c, single-referent leaves in l"""
    gg = D["groups"][g]
    return "c" if (len(gg.get("m") or []) > 1 or (gg.get("ch") or [])) else "l"


def fam_remove(D, fam, g):
    """Take a cluster out of a family completely — its listing and any region
       bucket it sits in. A cluster left behind in a region it no longer
       belongs to still renders there, so a move leaves a ghost."""
    F = D["families"]
    if fam not in F: return
    for k in ("c", "l"):
        if g in (F[fam].get(k) or []):
            F[fam][k].remove(g)
    for reg, lst in list((F[fam].get("rg") or {}).items()):
        if g in lst:
            lst.remove(g)
            if not lst: del F[fam]["rg"][reg]


def fam_add(D, fam, g):
    k = fam_list_for(D, g)
    D["families"][fam].setdefault(k, [])
    if g not in D["families"][fam][k]:
        D["families"][fam][k].append(g)
        D["families"][fam][k].sort()


def move_family(D, g, fam):
    gg = D["groups"][g]
    old = gg.get("f")
    if fam not in D["families"]:
        sys.exit("no family %r — families: %s" % (fam, ", ".join(sorted(D["families"]))))
    if gg.get("p"):
        sys.exit("%r is nested under %r; unnest it first" % (g, gg["p"]))
    fam_remove(D, old, g)
    for sub in [g] + list(descendants(D, g)):
        D["groups"][sub]["f"] = fam
    fam_add(D, fam, g)
    recount(D)
    return "%s: family %s -> %s (%s now %d Pokemon, %s now %d)" % (
        g, old, fam, old, D["families"][old]["n"], fam, D["families"][fam]["n"])


def normalize_leaf(D, g):
    """`leaf` marks a cluster holding a single own referent (children do not count)"""
    gg = D["groups"][g]
    if len(gg.get("m") or []) <= 1:
        gg["leaf"] = 1
    else:
        gg.pop("leaf", None)


def descendants(D, g):
    for c in D["groups"][g].get("ch") or []:
        yield c
        for d in descendants(D, c):
            yield d


def nest(D, child, parent):
    if child == parent:
        sys.exit("a cluster cannot hold itself")
    if child in descendants(D, parent) or parent in descendants(D, child):
        sys.exit("those two are already in one line of descent")
    c, p = D["groups"][child], D["groups"][parent]
    old = c.get("p")
    if old:
        D["groups"][old]["ch"] = [x for x in D["groups"][old].get("ch") or [] if x != child]
    else:
        fam_remove(D, c.get("f"), child)
    p.setdefault("ch", [])
    if child not in p["ch"]:
        p["ch"].append(child)
        p["ch"].sort()
    c["p"] = parent
    c["f"] = p.get("f")        # only the cluster being moved changes family;
                               # its descendants keep whatever family they had
    recount(D)
    return "%s now sits under %s (was %s); %s holds %d Pokemon" % (
        child, parent, old or "its family directly", parent, D["groups"][parent]["tn"])


def unnest(D, child):
    c = D["groups"][child]
    old = c.get("p")
    if not old:
        sys.exit("%r is already top level" % child)
    D["groups"][old]["ch"] = [x for x in D["groups"][old].get("ch") or [] if x != child]
    if not D["groups"][old]["ch"]:
        D["groups"][old].pop("ch", None)
    c.pop("p", None)
    fam_add(D, c.get("f"), child)
    recount(D)
    return "%s moved out of %s, back under family %s" % (child, old, c.get("f"))


def merge(D, src, dst):
    s, d = D["groups"][src], D["groups"][dst]
    if s.get("ch"):
        sys.exit("%r has children (%s) — nest or unnest those first" % (src, ", ".join(s["ch"])))
    moved = list(s.get("m") or [])
    d.setdefault("m", [])
    for m in moved:
        if m not in d["m"]:
            d["m"].append(m)
        D["referents"][m]["g"] = dst
    d["m"].sort()
    normalize_leaf(D, dst)
    p = s.get("p")
    if p:
        D["groups"][p]["ch"] = [x for x in D["groups"][p].get("ch") or [] if x != src]
        if not D["groups"][p]["ch"]:
            D["groups"][p].pop("ch", None)
    else:
        fam_remove(D, s.get("f"), src)
    del D["groups"][src]
    d["n"] = len(sub_species(D, dst))
    recount(D)
    D["meta"]["groups"] = len(D["groups"])
    return "%s folded into %s: moved %s; %s now has %d referents and %d Pokemon" % (
        src, dst, ", ".join(moved), dst, len(d["m"]),
        D["groups"][dst].get("tn", D["groups"][dst]["n"]))   # a leaf carries no tn


def regroup(D, new, parent, *children):
    """Make <new> inside <parent> (a cluster, or a family for a top-level one)
       and move the named clusters into it."""
    G, F = D["groups"], D["families"]
    if new in G:
        sys.exit("%r already exists" % new)
    if not children:
        sys.exit("name at least one cluster to move into %r" % new)
    into_family = parent in F and parent not in G
    if not into_family and parent not in G:
        sys.exit("no cluster or family called %r" % parent)
    fam = parent if into_family else G[parent].get("f")
    kind = F[fam]["k"] if into_family else G[parent].get("k")
    G[new] = {"k": kind, "m": [], "n": 0, "f": fam, "ch": []}
    normalize_leaf(D, new)      # a cluster with no referents of its own is still a leaf by this dataset's rule 
    if into_family:
        fam_add(D, fam, new)
    else:
        G[parent].setdefault("ch", []).append(new)
        G[parent]["ch"].sort()
        G[new]["p"] = parent
    for c in children:
        if c not in G:
            sys.exit("no cluster called %r" % c)
        old = G[c].get("p")
        if old:
            G[old]["ch"] = [x for x in G[old].get("ch") or [] if x != c]
            if not G[old]["ch"]: G[old].pop("ch", None)
        else:
            fam_remove(D, G[c].get("f"), c)
        G[c]["p"] = new
        G[c]["f"] = fam
        G[new]["ch"].append(c)
    G[new]["ch"].sort()
    recount(D)
    D["meta"]["groups"] = len(G)
    return "%s now holds %s, inside %s (%d Pokémon)" % (
        new, ", ".join(G[new]["ch"]), parent, G[new]["tn"])


def rename(D, old, new):
    """Rename a cluster, carrying every reference to it (parent, children,
       family lists, regions, its referents' home)."""
    G, F = D["groups"], D["families"]
    if old not in G: sys.exit("no cluster called %r" % old)
    if new in G: sys.exit("%r already exists" % new)
    g = G.pop(old); G[new] = g
    par = g.get("p")
    if par:
        G[par]["ch"] = sorted([new if x == old else x for x in G[par].get("ch") or []])
    else:
        fam = g.get("f")
        for k in ("c", "l"):
            lst = F[fam].get(k) or []
            if old in lst: lst[lst.index(old)] = new; lst.sort()
        for lst in (F[fam].get("rg") or {}).values():
            if old in lst: lst[lst.index(old)] = new; lst.sort()
    for c in g.get("ch") or []: G[c]["p"] = new
    for m in g.get("m") or []:
        if m in D["referents"]: D["referents"][m]["g"] = new
    recount(D)
    return "%r renamed to %r" % (old, new)


def split_family(D, old, new, *clusters):
    """Move top-level clusters out of <old> into a NEW family of the same kind."""
    F, G = D["families"], D["groups"]
    if old not in F: sys.exit("no family called %r" % old)
    if new in F: sys.exit("%r already exists" % new)
    if not clusters: sys.exit("name at least one cluster to move into %r" % new)
    src = F[old]
    F[new] = {"k": src.get("k"), "c": [], "l": [], "n": 0}
    if src.get("b"): F[new]["b"] = src["b"]
    for c in clusters:
        if c not in G: sys.exit("no cluster called %r" % c)
        if G[c].get("p"): sys.exit("%r is nested under %r, not top level" % (c, G[c]["p"]))
        if G[c].get("f") != old: sys.exit("%r is not in %r" % (c, old))
        fam_remove(D, old, c)
        G[c]["f"] = new
        # the family total counts every group filed under it, so the subtree
        # has to come along — except descendants deliberately filed elsewhere
        for sub in descendants(D, c):
            if G[sub].get("f") == old: G[sub]["f"] = new
        fam_add(D, new, c)
    if src.get("b"):
        for defs in (D.get("branches") or {}).values():
            for d in defs:
                if old in d[1] and new not in d[1]: d[1].append(new); d[1].sort()
    recount(D)
    D["meta"]["families"] = len(F)
    return "%s split: %s keeps %d Pokemon, %s takes %d" % (
        old, old, F[old]["n"], new, F[new]["n"])


def rename_family(D, old, new):
    """Rename a family, carrying its clusters, branch entries and listings."""
    F, G = D["families"], D["families"] and D["groups"]
    if old not in F: sys.exit("no family called %r" % old)
    if new in F: sys.exit("%r already exists" % new)
    F[new] = F.pop(old)
    for g, v in G.items():
        if v.get("f") == old: v["f"] = new
    for defs in (D.get("branches") or {}).values():
        for d in defs:
            d[1][:] = [new if x == old else x for x in d[1]]
    recount(D)
    return "family %r renamed to %r" % (old, new)


def drop_empty_cluster(D, g):
    """A cluster with no referents of its own and no children is a node the
       page would draw with nothing inside it. Folding the last referent out
       of a leaf cluster should take the cluster with it; a grouping cluster
       that still has children is left alone, since holding children is its
       whole job."""
    G = D["groups"]
    v = G.get(g)
    if not v or (v.get("m") or []) or (v.get("ch") or []): return None
    par = v.get("p")
    if par in G:
        G[par]["ch"] = [c for c in (G[par].get("ch") or []) if c != g]
        if not G[par]["ch"]: G[par].pop("ch", None)
    if v.get("f") in D["families"]: fam_remove(D, v["f"], g)
    del G[g]
    D["meta"]["groups"] = len(G)
    return g


def merge_ref(D, src, dst):
    """Fold one referent into another: the Pokemon join, the name disappears
       from every species' design list, and the cluster drops the stray."""
    R, G, S = D["referents"], D["groups"], D["species"]
    if src not in R: sys.exit("no referent called %r" % src)
    if dst not in R: sys.exit("no referent called %r" % dst)
    a, b = R[dst], R[src]
    a["s"] = sorted(set(a["s"]) | set(b["s"]))
    if not a.get("w") and b.get("w"): a["w"] = b["w"]
    # the design lists hold display strings, which may differ in case
    low = src.lower()
    for i, sp in S.items():
        sp[1] = [x for n, x in enumerate(sp[1])
                 if x.lower() != low or dst.lower() not in [y.lower() for y in sp[1]]]
        sp[1] = [dst if x.lower() == low else x for x in sp[1]]
        seen, out = set(), []
        for x in sp[1]:
            if x.lower() in seen: continue
            seen.add(x.lower()); out.append(x)
        sp[1] = out
    for slug, fm in (D.get("forms") or {}).items():
        own = fm.get("own")
        if own:
            fm["own"] = [dst if x.lower() == low else x for x in own]
    fr = D.get("formrefs") or {}
    if low in fr:
        fr.setdefault(dst.lower(), {}).update(fr.pop(low))
    g = b.get("g")
    if g in G and src in (G[g].get("m") or []):
        G[g]["m"].remove(src)
        normalize_leaf(D, g)
    del R[src]
    for gg, v in G.items():
        if src in (v.get("m") or []): v["m"].remove(src)
    gone = drop_empty_cluster(D, g)
    recount(D)
    D["meta"]["referents"] = len(R)
    return "%r folded into %r — now %d Pokemon%s" % (
        src, dst, len(a["s"]),
        ("; empty cluster %r dropped" % gone) if gone else "")


def move_ref(D, ref, cluster):
    """Move a referent into another cluster — for the ones that landed in a
       cluster by name collision rather than by meaning."""
    R, G = D["referents"], D["groups"]
    if ref not in R: sys.exit("no referent called %r" % ref)
    if cluster not in G: sys.exit("no cluster called %r" % cluster)
    old = R[ref].get("g")
    if old == cluster: sys.exit("%r is already in %r" % (ref, cluster))
    if old in G and ref in (G[old].get("m") or []):
        G[old]["m"].remove(ref)
        normalize_leaf(D, old)
    G[cluster].setdefault("m", []).append(ref)
    G[cluster]["m"].sort()
    normalize_leaf(D, cluster)
    R[ref]["g"] = cluster
    R[ref]["k"] = G[cluster].get("k") or R[ref].get("k")
    R[ref].pop("i", None)          # placed by hand now, not guessed
    gone = drop_empty_cluster(D, old)
    recount(D)
    return "%r moved from %r to %r (now %s)%s" % (
        ref, old, cluster, R[ref]["k"],
        ("; empty cluster %r dropped" % gone) if gone else "")


def _disp_of(D, ref):
    """What the species panels print for a referent — the stored display
       spelling if it has one, else the key itself."""
    return (D["referents"].get(ref) or {}).get("d") or ref


def rename_ref(D, old, new):
    """Rename a referent everywhere it is named: the key, its cluster's list,
       every species' design list, the form overrides. A capitalised <new>
       is kept as the display spelling over a lower-case key, the way the
       generator stores proper nouns."""
    R, G, S = D["referents"], D["groups"], D["species"]
    if old not in R: sys.exit("no referent called %r" % old)
    key = new.lower()
    if key != old and key in R:
        sys.exit("%r already exists — merge-ref if they are the same thing" % key)
    was_disp = _disp_of(D, old)
    v = R.pop(old)
    if key != new: v["d"] = new
    else: v.pop("d", None)
    R[key] = v
    for g, gv in G.items():
        m = gv.get("m") or []
        if old in m:
            gv["m"] = sorted([x for x in m if x != old] + [key])
    low = was_disp.lower()
    for i, sp in S.items():
        sp[1] = [new if x.lower() == low else x for x in sp[1]]
    for slug, fm in (D.get("forms") or {}).items():
        if fm.get("own"):
            fm["own"] = [new if x.lower() == low else x for x in fm["own"]]
    fr = D.get("formrefs") or {}
    if old in fr: fr[key] = fr.pop(old)
    recount(D)
    return "%r renamed to %r (shown as %r)" % (old, key, new)


def add_ref(D, new, cluster, *species):
    """Add a referent Bulbapedia names and the build missed. It takes the
       cluster's category, the Pokemon are named by id, and it appears in each
       of their design lists — the same shape the generator would have made.
       Link it afterwards with set-wiki or set-url, and mark it with
       set-allusion if the design only nods at it."""
    R, G, S = D["referents"], D["groups"], D["species"]
    key = new.lower()
    if key in R: sys.exit("%r already exists — add the Pokemon to it instead" % key)
    if cluster not in G: sys.exit("no cluster called %r" % cluster)
    if not species: sys.exit("name at least one Pokemon by id")
    ids = sorted({int(x) for x in species})
    stray = [i for i in ids if str(i) not in S]
    if stray: sys.exit("no such Pokemon: %s" % stray)
    R[key] = {"g": cluster, "k": G[cluster].get("k"), "s": ids}
    if key != new: R[key]["d"] = new
    G[cluster].setdefault("m", []).append(key)
    G[cluster]["m"].sort()
    normalize_leaf(D, cluster)
    for i in ids:
        sp = S[str(i)]
        if new not in sp[1]: sp[1].append(new)
    recount(D)
    D["meta"]["referents"] = len(R)
    return "%r added to %r (%s) — %s" % (
        key, cluster, R[key]["k"], ", ".join("#%d %s" % (i, S[str(i)][0]) for i in ids))


def split_ref(D, src, new, *species):
    """Break a compound referent in two. A name like "highwayman dick turpin"
       makes two claims — a role and a man — and a reader cannot follow either
       to an article. The new referent lands in the same cluster with the same
       category and, by default, the same Pokemon, because a compound name is
       usually two readings of one design rather than a split of the roster;
       name species ids to give the new one only those. <src> keeps what it
       had, so rename it afterwards to whatever half is left."""
    R, G, S = D["referents"], D["groups"], D["species"]
    if src not in R: sys.exit("no referent called %r" % src)
    key = new.lower()
    if key in R: sys.exit("%r already exists" % key)
    ids = [int(x) for x in species] if species else list(R[src]["s"])
    stray = [i for i in ids if i not in R[src]["s"]]
    if stray: sys.exit("%r does not cover %s" % (src, stray))
    v = R[src]
    R[key] = {"g": v.get("g"), "k": v.get("k"), "s": sorted(ids)}
    if key != new: R[key]["d"] = new
    if v.get("x"): R[key]["x"] = 1
    if v.get("i"): R[key]["i"] = 1
    g = v.get("g")
    if g in G:
        G[g].setdefault("m", []).append(key)
        G[g]["m"].sort()
        normalize_leaf(D, g)
    for i in ids:
        sp = S.get(str(i)) or S.get(i)
        if sp and new not in sp[1]: sp[1].append(new)
    recount(D)
    D["meta"]["referents"] = len(R)
    return "%r split out of %r — %d Pokemon, cluster %r" % (key, src, len(ids), g)


def set_meta(D, ref, flag="on"):
    """Mark a referent as something from inside the franchise — the Gracidea,
       a Poke Ball, Puka from the anime — or take the mark off. These are real
       readings Bulbapedia makes, but they point at the games rather than at
       the world, so there is no article to reach and nothing to check them
       against; the page says so rather than letting them pass as design
       sources read off the world. A Wikipedia link is still fine where one
       exists — Ash Ketchum has an article; the mark is about where the
       reading comes from, not about whether anyone has written it up. Where a real-world twin already exists,
       prefer merge-ref: Necrozma's bat was better served by the bat."""
    R = D["referents"]
    if ref not in R: sys.exit("no referent called %r" % ref)
    if flag not in ("on", "off"): sys.exit("on or off")
    was = "in-universe" if R[ref].get("mr") else "from the world"
    if flag == "on": R[ref]["mr"] = 1
    else: R[ref].pop("mr", None)
    return "%r: %s -> %s" % (ref, was,
                             "in-universe" if flag == "on" else "from the world")


def set_allusion(D, ref, flag="on"):
    """Mark a referent as something the design alludes to rather than is drawn
       from, or take the mark off. The page prints these softer, because
       "a nod to" and "based on" are not the same claim."""
    R = D["referents"]
    if ref not in R: sys.exit("no referent called %r" % ref)
    if flag not in ("on", "off"): sys.exit("on or off")
    was = "allusion" if R[ref].get("x") else "design source"
    if flag == "on": R[ref]["x"] = 1
    else: R[ref].pop("x", None)
    return "%r: %s -> %s" % (ref, was, "allusion" if flag == "on" else "design source")


def set_wiki(D, ref, title=""):
    """Point a referent at a Wikipedia article, or clear the link. An empty
       title is the honest answer when no article is actually about it —
       better than sending a reader to a disambiguation page.

       A title may name a section — "Aphrodite#Symbolism" — and the section is
       kept apart in `ws`, because `w` is fed straight to Wikipedia's API by
       the geo and audit passes and an anchor is not a page title."""
    R = D["referents"]
    if ref not in R: sys.exit("no referent called %r" % ref)
    if title.lower().startswith(("http://", "https://")):
        sys.exit("that is a URL, not an article title — use set-url for an "
                 "off-Wikipedia source, or pass just the title")
    was = R[ref].get("w") or "-"
    if was != "-" and R[ref].get("ws"): was += "#" + R[ref]["ws"]
    title, _, section = title.partition("#")
    title, section = title.strip(), section.strip()
    if title:
        R[ref]["w"] = title
        R[ref].pop("u", None)          # a real article beats a stand-in link
        if section: R[ref]["ws"] = section
        else: R[ref].pop("ws", None)
    else:
        R[ref].pop("w", None); R[ref].pop("ws", None)
    now = title + ("#" + section if section else "") if title else "(none)"
    return "%r wiki: %s -> %s" % (ref, was, now)


def set_url(D, ref, url=""):
    """Point a referent at a source that is not a Wikipedia article — a
       Wiktionary entry for an idiom, say. It is only read when `w` is empty,
       so the geo and audit passes never see it; the page names the site from
       the URL's own host."""
    R = D["referents"]
    if ref not in R: sys.exit("no referent called %r" % ref)
    if url and not url.lower().startswith(("http://", "https://")):
        sys.exit("a full http(s) URL, or nothing to clear it")
    was = R[ref].get("u") or "-"
    if url:
        if R[ref].get("w"):
            sys.exit("%r already has the Wikipedia article %r — clear it with "
                     "set-wiki first if the other source is the better one"
                     % (ref, R[ref]["w"]))
        R[ref]["u"] = url
    else: R[ref].pop("u", None)
    return "%r url: %s -> %s" % (ref, was, url or "(none)")


def set_region(D, cluster, family, region):
    """Put a top-level cluster in a family's region bucket — moving it between
       families if need be. A family that uses regions renders them instead of
       its clusters, so a cluster in no region is invisible."""
    F, G = D["families"], D["groups"]
    if cluster not in G: sys.exit("no cluster called %r" % cluster)
    if family not in F: sys.exit("no family called %r" % family)
    if G[cluster].get("p"): sys.exit("%r is nested under %r, not top level" % (cluster, G[cluster]["p"]))
    old = G[cluster].get("f")
    for fam in (old, family):
        if fam not in F: continue
        for k in ("c", "l"):
            if cluster in (F[fam].get(k) or []): F[fam][k].remove(cluster)
        for reg, lst in list((F[fam].get("rg") or {}).items()):
            if cluster in lst:
                lst.remove(cluster)
                if not lst: del F[fam]["rg"][reg]
    G[cluster]["f"] = family
    for sub in descendants(D, cluster):
        if G[sub].get("f") == old: G[sub]["f"] = family
    for m in (G[cluster].get("m") or []):
        if m in D["referents"]: D["referents"][m]["g"] = cluster
    fam_add(D, family, cluster)
    F[family].setdefault("rg", {}).setdefault(region, [])
    if cluster not in F[family]["rg"][region]:
        F[family]["rg"][region].append(cluster)
        F[family]["rg"][region].sort()
    recount(D)
    return "%r -> %s / %s (was %s)" % (cluster, family, region, old)


def normalize_case(D):
    """Give every referent one spelling, taken from Bulbapedia's own.

       Keys stay lowercase — everything looks referents up by them — but a
       referent whose source text capitalises it (Curupira, El Dorado, RPG
       mimic) carries that spelling in `d`, and the page shows `d` wherever it
       shows a name. The design lists are rewritten to match, so the same
       referent never reads two ways."""
    R, S, FM = D["referents"], D["species"], D.get("forms") or {}
    seen = {}
    def note(x):
        k = x.lower()
        if k in R: seen.setdefault(k, {}).setdefault(x, 0)
        if k in R: seen[k][x] += 1
    for sp in S.values():
        for x in sp[1]: note(x)
    for fm in FM.values():
        for x in (fm.get("own") or []): note(x)
    chosen, conflicts = {}, 0
    # A spelling set by hand wins: this pass rewrites the design strings to
    # match, so the evidence it was chosen from is gone by the next run.
    for k, v in R.items():
        if v.get("d") and v["d"] != k: chosen[k] = v["d"]
    for k, counts in seen.items():
        if k in chosen: continue
        if len(counts) > 1: conflicts += 1
        # Where the source spells it two ways, take the capitalised one: a
        # proper noun written mid-sentence loses its capital far more often
        # than a common noun gains one.
        if len(counts) > 1:
            caps = [x for x in counts if x != k]
            best = sorted(caps, key=lambda x: (-counts[x], x))[0] if caps else k
        else:
            best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        if best != k: chosen[k] = best
    for k, v in R.items():
        if k in chosen: v["d"] = chosen[k]
        else: v.pop("d", None)
    # one spelling in the design lists too
    fixed = 0
    for sp in S.values():
        for i, x in enumerate(sp[1]):
            want = chosen.get(x.lower(), x.lower() if x.lower() in R else x)
            if x != want: sp[1][i] = want; fixed += 1
    for fm in FM.values():
        own = fm.get("own")
        if not own: continue
        for i, x in enumerate(own):
            want = chosen.get(x.lower(), x.lower() if x.lower() in R else x)
            if x != want: own[i] = want; fixed += 1
    return "%d referents carry a capitalised spelling (%d had been spelled two ways); %d strings rewritten to match" % (
        len(chosen), conflicts, fixed)


def split_cluster(D, src, new, *refs):
    """Move some of a cluster's referents into a new sibling cluster — for a
       cluster that turns out to hold two different senses of its name."""
    G, R = D["groups"], D["referents"]
    if src not in G: sys.exit("no cluster called %r" % src)
    if new in G: sys.exit("%r already exists" % new)
    if not refs: sys.exit("name at least one referent to move into %r" % new)
    own = G[src].get("m") or []
    missing = [r for r in refs if r not in own]
    if missing: sys.exit("not in %r: %s" % (src, ", ".join(missing)))
    if len(refs) >= len(own): sys.exit("that would empty %r" % src)
    G[new] = {"k": G[src].get("k"), "m": sorted(refs), "n": 0, "f": G[src].get("f")}
    if G[src].get("p"): G[new]["p"] = G[src]["p"]
    for r in refs:
        own.remove(r)
        R[r]["g"] = new
    normalize_leaf(D, src); normalize_leaf(D, new)
    par = G[src].get("p")
    if par:
        G[par].setdefault("ch", []).append(new); G[par]["ch"].sort()
    else:
        fam_add(D, G[src]["f"], new)
        for reg, lst in ((D["families"][G[src]["f"]].get("rg")) or {}).items():
            if src in lst: lst.append(new); lst.sort(); break
    recount(D)
    D["meta"]["groups"] = len(G)
    return "%s split: %s keeps %s; %s takes %s" % (
        src, src, ", ".join(G[src]["m"]), new, ", ".join(G[new]["m"]))


def set_kind(D, name, kind):
    kinds = D["meta"].get("kinds") or []
    if kind not in kinds + ["unclassified"]:
        sys.exit("kind must be one of: %s" % ", ".join(kinds))
    hit = []
    if name.lower() in D["referents"]:
        D["referents"][name.lower()]["k"] = kind
        D["referents"][name.lower()].pop("i", None)
        hit.append("referent")
    if name in D["groups"]:
        D["groups"][name]["k"] = kind
        hit.append("cluster")
    if not hit:
        sys.exit("no referent or cluster called %r" % name)
    return "%s (%s): category -> %s" % (name, "/".join(hit), kind)


WRITES = {"move-family": move_family, "nest": nest, "unnest": unnest,
          "merge": merge, "regroup": regroup, "rename": rename,
          "split-family": split_family, "rename-family": rename_family,
          "merge-ref": merge_ref, "move-ref": move_ref, "split-cluster": split_cluster,
          "split-ref": split_ref, "rename-ref": rename_ref, "set-allusion": set_allusion, "set-meta": set_meta,
          "add-ref": add_ref,
          "set-kind": set_kind, "set-wiki": set_wiki, "set-url": set_url,
          "set-region": set_region,
          "normalize-case": lambda D: normalize_case(D),
          "recount": lambda D: recount(D)}


# ---------- surviving a rebuild ----------

def overlay_of(D):
    """The hand-made structure, read straight off the current dataset: where
       everything sits, never the counts, which are always recomputed."""
    O = {"families": {}, "groups": {}, "referents": {}}
    for fam, f in D["families"].items():
        O["families"][fam] = {"k": f.get("k"), "b": f.get("b")}
    for g, v in D["groups"].items():
        O["groups"][g] = {"f": v.get("f"), "p": v.get("p"), "k": v.get("k"),
                          "m": list(v.get("m") or [])}
    for r, v in D["referents"].items():
        O["referents"][r] = {"g": v.get("g"), "k": v.get("k"), "w": v.get("w"),
                             "ws": v.get("ws"), "u": v.get("u"),
                             "x": v.get("x"), "mr": v.get("mr")}
    return O


def patch_apply(D, fresh_path):
    """Replay this dataset's structure onto a freshly generated map_data.json.
       Anything the new build no longer has is reported, never forced."""
    with open(fresh_path, encoding="utf-8") as fh:
        N = json.load(fh)
    O = overlay_of(D)
    G, R, F = N["groups"], N["referents"], N["families"]
    made_f = made_g = moved = recat = 0
    missing = []
    for fam, meta in O["families"].items():
        if fam not in F:
            F[fam] = {"k": meta.get("k"), "c": [], "l": [], "n": 0}
            if meta.get("b"): F[fam]["b"] = meta["b"]
            made_f += 1
    for g, meta in O["groups"].items():
        if g not in G:
            # a grouping cluster this session invented: recreate it empty
            if not meta.get("m"):
                G[g] = {"k": meta.get("k"), "m": [], "n": 0, "f": meta.get("f"), "ch": []}
                made_g += 1
            else:
                missing.append("cluster " + g)
                continue
        gg = G[g]
        if meta.get("f"): gg["f"] = meta["f"]
        if meta.get("k"): gg["k"] = meta["k"]
        gg.pop("p", None)
    # parents, after every cluster exists
    for g, meta in O["groups"].items():
        if g in G and meta.get("p") and meta["p"] in G:
            G[g]["p"] = meta["p"]
    # Rebuild every child list from the parents actually set, so clusters the
    # overlay has never heard of — ones the generator added, or ones this
    # session merged away and the rebuild brought back — stay linked instead
    # of dangling off a parent that no longer lists them.
    kids = {}
    for g, v in G.items():
        par = v.get("p")
        if par and par in G: kids.setdefault(par, []).append(g)
    for g, v in G.items():
        ch = sorted(kids.get(g, []))
        if ch: v["ch"] = ch
        else: v.pop("ch", None)
    for r, meta in O["referents"].items():
        if r not in R:
            missing.append("referent " + r)
            continue
        if meta.get("g") and meta["g"] in G and R[r].get("g") != meta["g"]:
            old = R[r].get("g")
            if old in G and r in (G[old].get("m") or []): G[old]["m"].remove(r)
            R[r]["g"] = meta["g"]
            if r not in (G[meta["g"]].get("m") or []):
                G[meta["g"]].setdefault("m", []).append(r); G[meta["g"]]["m"].sort()
            moved += 1
        if meta.get("k") and R[r].get("k") != meta["k"]:
            R[r]["k"] = meta["k"]; R[r].pop("i", None); recat += 1
        if meta.get("w"): R[r]["w"] = meta["w"]
        if meta.get("ws"): R[r]["ws"] = meta["ws"]
        if meta.get("u"): R[r]["u"] = meta["u"]
        if meta.get("x"): R[r]["x"] = 1
        if meta.get("mr"): R[r]["mr"] = 1
    # rebuild the family listings and every count from the result
    for fam in F:
        F[fam]["c"] = []; F[fam]["l"] = []
    for g, v in G.items():
        normalize_leaf(N, g)
        if not v.get("p") and v.get("f") in F: fam_add(N, v["f"], g)
    recount(N)
    N["meta"]["families"] = len(F); N["meta"]["groups"] = len(G)
    N["meta"]["referents"] = len(R)
    # anything the fresh build has that the overlay does not: either new from
    # the generator, or something this session merged away. Worth a look, not
    # a silent decision.
    unknown = [g for g in G if g not in O["groups"]][:12]
    unknown_r = [r for r in R if r not in O["referents"]][:12]
    bad = check(N, quiet=True)
    out = fresh_path + ".patched.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(N, fh, ensure_ascii=False, separators=(",", ":"))
    lines = ["replayed onto %s" % fresh_path,
             "  %d families created, %d clusters recreated, %d referents refiled, %d recategorised"
             % (made_f, made_g, moved, recat),
             "  %d overlay entries the new build no longer has%s"
             % (len(missing), (": " + ", ".join(missing[:5])) if missing else ""),
             "  %d clusters / %d referents the overlay does not know (new upstream, or merged away here)%s"
             % (len(unknown), len(unknown_r),
                (": " + ", ".join(unknown[:6])) if unknown else ""),
             "  integrity %s" % ("clean" if not bad else "%d problems" % len(bad)),
             "  written to %s" % out]
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:] if a not in ("--dry", "--bust")]
    dry = "--dry" in sys.argv
    bust = "--bust" in sys.argv
    if not args:
        return print(__doc__)
    cmd, rest = args[0], args[1:]
    D = load()
    if cmd == "show":
        for n in rest or []:
            show(D, n)
            print()
        return
    if cmd == "grep":
        return grep(D, " ".join(rest))
    if cmd == "species":
        return species_cmd(D, " ".join(rest))
    if cmd == "where":
        return where(D, " ".join(rest))
    if cmd == "published":
        return published_cmd(rest)
    if cmd == "check":
        stop = guard_build(D) or guard_published()
        if stop: print(stop)
        return sys.exit(1 if (check(D) or stop) else 0)
    if cmd == "rebased":
        rec = stamp_write(D)
        print("recorded: the corrections in data/map_data.json sit on build %s" % rec["build"])
        return
    if cmd == "patch":
        if (rest[:1] or [""])[0] != "apply" or len(rest) < 2:
            sys.exit("patch apply <fresh map_data.json>")
        print(patch_apply(D, rest[1])); return
    if cmd == "build":
        stop = guard_build(D) or guard_published()
        if stop: print(stop); return sys.exit(1)
        print(build(D, bust)); return
    if cmd in WRITES:
        stop = guard_build(D) or guard_published()
        if stop: print(stop); return sys.exit(1)
        before = len(check(D, quiet=True))
        summary = WRITES[cmd](D, *rest)
        bad = check(D, quiet=True)
        print(summary)
        if len(bad) > before:
            print("REFUSED — this edit would break integrity:")
            for b in bad[:10]:
                print("  ", b)
            return sys.exit(1)
        if dry:
            return print("(dry run — nothing saved)")
        save(D)
        print("saved %s and rebuilt %s — integrity clean" % (
            os.path.relpath(DATA, HERE), os.path.relpath(DIST, HERE)))
        return
    print("unknown command %r" % cmd)
    print(__doc__)


if __name__ == "__main__":
    main()
