#!/usr/bin/env python3
"""Exercise every write command against a copy of the real dataset.

    python3 -I tests/test_flagkit.py

No test framework: it prints a line per case and exits non-zero on the first
failure. Every case ends with the integrity check, because that is the promise
flagkit makes — a command either leaves the data sound or refuses to save.
"""
import copy, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flagkit as fk

PASS, FAIL = [], []


def case(name):
    def wrap(fn):
        D = json.loads(json.dumps(BASE))
        try:
            fn(D)
            bad = fk.check(D, quiet=True)
            assert not bad, "integrity broke: %s" % bad[:3]
            PASS.append(name)
            print("  ok    %s" % name)
        except AssertionError as e:
            FAIL.append((name, str(e)))
            print("  FAIL  %s — %s" % (name, e))
        except SystemExit as e:
            FAIL.append((name, "exited: %s" % e))
            print("  FAIL  %s — command exited: %s" % (name, e))
        return fn
    return wrap


def pick(D, pred, what):
    for k, v in sorted(D["groups"].items()):
        if pred(v): return k
    raise AssertionError("no cluster to test %s with" % what)


print("loading the real dataset as a fixture…")
BASE = fk.load()
print("  %d clusters, %d referents, %d families\n" % (
    len(BASE["groups"]), len(BASE["referents"]), len(BASE["families"])))

print("baseline")
bad = fk.check(BASE, quiet=True)
if bad:
    print("  FAIL  the committed dataset is not clean: %s" % bad[:3]); sys.exit(1)
print("  ok    committed dataset is clean\n")

print("write commands")


@case("nest keeps the moved cluster's subtree in its own family")
def _(D):
    child = pick(D, lambda v: not v.get("p") and (v.get("ch") or []), "nest")
    parent = pick(D, lambda v: not v.get("p") and v.get("f") != D["groups"][child].get("f"), "nest")
    kids = list(D["groups"][child].get("ch") or [])
    before = {k: D["groups"][k].get("f") for k in kids}
    fk.nest(D, child, parent)
    assert D["groups"][child]["p"] == parent
    assert D["groups"][child]["f"] == D["groups"][parent]["f"]
    for k in kids:
        assert D["groups"][k].get("f") == before[k], "%s changed family" % k


@case("unnest puts a cluster back under its family")
def _(D):
    child = pick(D, lambda v: v.get("p"), "unnest")
    fk.unnest(D, child)
    assert not D["groups"][child].get("p")
    fam = D["groups"][child]["f"]
    listed = (D["families"][fam].get("c") or []) + (D["families"][fam].get("l") or [])
    assert child in listed


@case("regroup gathers clusters and carries their Pokemon")
def _(D):
    fam = "Instruments"
    kids = [g for g, v in D["groups"].items() if v.get("f") == fam and not v.get("p")][:3]
    want = set()
    for k in kids: want |= fk.sub_species(D, k)
    fk.regroup(D, "test group", fam, *kids)
    assert set(D["groups"]["test group"]["ch"]) == set(kids)
    assert D["groups"]["test group"]["tn"] == len(want)
    assert D["groups"]["test group"].get("leaf") == 1, "no own referents, so still a leaf"


@case("merge folds a cluster's referents into another")
def _(D):
    src = pick(D, lambda v: not (v.get("ch") or []) and len(v.get("m") or []) == 1, "merge")
    dst = pick(D, lambda v: not (v.get("ch") or []) and len(v.get("m") or []) > 1, "merge")
    moved = list(D["groups"][src]["m"])
    fk.merge(D, src, dst)
    assert src not in D["groups"]
    for m in moved:
        assert m in D["groups"][dst]["m"] and D["referents"][m]["g"] == dst


@case("merge-ref folds a referent and rewrites every design list")
def _(D):
    singles = [r for r, v in sorted(D["referents"].items()) if len(v["s"]) == 1]
    src, dst = singles[0], singles[1]
    want = set(D["referents"][src]["s"]) | set(D["referents"][dst]["s"])
    fk.merge_ref(D, src, dst)
    assert src not in D["referents"]
    assert set(D["referents"][dst]["s"]) == want
    for i, sp in D["species"].items():
        assert all(x.lower() != src.lower() for x in sp[1]), "%s still cited by %s" % (src, i)
    dead = [x for sp in D["species"].values() for x in sp[1] if x.lower() not in D["referents"]]
    assert not dead, "design strings left dangling: %s" % dead[:3]


@case("split-family carries the subtree, not just the top cluster")
def _(D):
    fam = "Life sciences"
    top = [g for g, v in D["groups"].items() if v.get("f") == fam and not v.get("p")][:2]
    subtree = set()
    for g in top: subtree |= fk.sub_species(D, g)
    # what the clusters own directly — the value the old, broken split produced
    own = set()
    for g in top:
        for m in (D["groups"][g].get("m") or []):
            own |= set(D["referents"][m]["s"])
    fk.split_family(D, fam, "test family", *top)
    got = D["families"]["test family"]["n"]
    assert got > len(own), "only the top clusters moved: %d vs own %d" % (got, len(own))
    assert got <= len(subtree), "counted more than the subtree holds: %d > %d" % (got, len(subtree))
    # and the old family must have given those Pokemon up
    assert D["families"][fam]["n"] < len(fk.fam_species(D, fam)) + len(subtree)


@case("rename and rename-family carry every reference")
def _(D):
    g = pick(D, lambda v: v.get("p"), "rename")
    par, refs = D["groups"][g]["p"], list(D["groups"][g].get("m") or [])
    fk.rename(D, g, "renamed cluster")
    assert "renamed cluster" in D["groups"][par]["ch"] and g not in D["groups"][par]["ch"]
    for m in refs: assert D["referents"][m]["g"] == "renamed cluster"
    fk.rename_family(D, "Instruments", "Noisemakers")
    assert "Instruments" not in D["families"]
    assert not [1 for v in D["groups"].values() if v.get("f") == "Instruments"]


@case("set-region refiles a cluster and keeps it visible in a region")
def _(D):
    fam = "European folklore"
    reg = "Celtic & British Isles"
    src = (D["families"]["Other folklore"]["rg"]["Not tied to one place"])[0]
    fk.set_region(D, src, fam, reg)
    assert D["groups"][src]["f"] == fam
    assert src in D["families"][fam]["rg"][reg], "a cluster in no region is invisible on the page"
    listed = (D["families"][fam].get("c") or []) + (D["families"][fam].get("l") or [])
    assert src in listed
    for other, f in D["families"].items():
        if other == fam:
            continue
        for lst in (f.get("rg") or {}).values():
            assert src not in lst, "left behind in %s" % other


@case("normalize-case gives each referent one spelling, and keeps a hand-set one")
def _(D):
    # a referent the source text capitalises
    r = next(r for r, v in sorted(D["referents"].items()) if v.get("d"))
    want = D["referents"][r]["d"]
    fk.normalize_case(D)
    assert D["referents"][r]["d"] == want, "a settled spelling must survive a re-run"
    for sp in D["species"].values():
        for x in sp[1]:
            k = x.lower()
            if k in D["referents"]:
                assert x == (D["referents"][k].get("d") or k), \
                    "%s is written two ways" % k
    # and one set by hand wins over whatever the strings say
    other = next(r for r, v in sorted(D["referents"].items()) if not v.get("d"))
    D["referents"][other]["d"] = "Deliberate Spelling"
    fk.normalize_case(D)
    assert D["referents"][other]["d"] == "Deliberate Spelling"


@case("set-wiki sets a title and clears it")
def _(D):
    r = next(r for r, v in sorted(D["referents"].items()) if v.get("w"))
    fk.set_wiki(D, r, "Some Article")
    assert D["referents"][r]["w"] == "Some Article"
    fk.set_wiki(D, r)
    assert "w" not in D["referents"][r], "an empty title must remove the link, not blank it"


@case("move-ref rehomes a referent and takes its cluster's category")
def _(D):
    src = pick(D, lambda v: len(v.get("m") or []) > 1, "move-ref")
    ref = D["groups"][src]["m"][0]
    dst = pick(D, lambda v: v.get("k") and v.get("k") != D["groups"][src].get("k"), "move-ref")
    fk.move_ref(D, ref, dst)
    assert D["referents"][ref]["g"] == dst
    assert ref in D["groups"][dst]["m"] and ref not in D["groups"][src]["m"]
    assert D["referents"][ref]["k"] == D["groups"][dst]["k"]
    assert not D["referents"][ref].get("i"), "a hand-placed referent is no longer a guess"


@case("set-kind recategorises and clears the inferred flag")
def _(D):
    r = next(r for r, v in sorted(D["referents"].items()) if v.get("i"))
    fk.set_kind(D, r, "mythology")
    assert D["referents"][r]["k"] == "mythology" and not D["referents"][r].get("i")


print("\nguard rails (these must refuse, not corrupt)")


def refuses(name, fn):
    D = json.loads(json.dumps(BASE))
    try:
        fn(D)
    except SystemExit:
        PASS.append(name); print("  ok    %s" % name); return
    FAIL.append((name, "it did not refuse")); print("  FAIL  %s — it did not refuse" % name)


refuses("nest refuses a cycle", lambda D: fk.nest(D, "tree", "aspen"))
refuses("regroup refuses a name already taken", lambda D: fk.regroup(D, "tree", "Other plants", "aspen"))
refuses("split-family refuses a nested cluster", lambda D: fk.split_family(D, "Other plants", "x", "aspen"))
refuses("merge-ref refuses an unknown referent", lambda D: fk.merge_ref(D, "no such referent", "tree"))

print("\nrebuild path")
D = json.loads(json.dumps(BASE))
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
    stripped = json.loads(json.dumps(BASE))
    # a crude stand-in for a regenerated build: flatten some nesting away
    moved = 0
    for g, v in list(stripped["groups"].items()):
        if v.get("p") and moved < 40:
            v.pop("p", None); moved += 1
    for v in stripped["groups"].values(): v.pop("ch", None)
    json.dump(stripped, fh)
    fresh = fh.name
report = fk.patch_apply(D, fresh)
patched = json.load(open(fresh + ".patched.json"))
same = [g for g in patched["groups"] if g in BASE["groups"]
        and (patched["groups"][g].get("p") != BASE["groups"][g].get("p")
             or patched["groups"][g].get("f") != BASE["groups"][g].get("f"))]
if same:
    FAIL.append(("patch apply restores placement", "%d clusters differ" % len(same)))
    print("  FAIL  patch apply restores placement — %d clusters differ" % len(same))
else:
    PASS.append("patch apply restores placement")
    print("  ok    patch apply restores placement (%d clusters flattened, all put back)" % moved)
if fk.check(patched, quiet=True):
    FAIL.append(("patched build is clean", "integrity problems"))
    print("  FAIL  patched build is clean")
else:
    PASS.append("patched build is clean"); print("  ok    patched build is clean")
for p in (fresh, fresh + ".patched.json"):
    try: os.unlink(p)
    except OSError: pass

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
sys.exit(1 if FAIL else 0)
