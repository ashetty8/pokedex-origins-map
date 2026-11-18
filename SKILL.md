---
name: pokedex-flags
description: Work through the open flags on the Pokédex Origins Map artifact — read them from the artifact database, diagnose each against the local dataset copy with flagkit.py, fix the page or the data, publish, and mark the flag applied. Use when the user says "flags", "review flags", "fix the flags", or names a flag on that map.
---

# Pokédex Origins Map — flag loop

The map is artifact `https://claude.ai/artifact/FP9NhVBPPv8ozSKYAfhBR8`. Its viewers file
flags into the artifact database collection `corrections`. This skill is the cheap loop for
clearing them.

The project is a git repo rooted at this skill's directory (`ashetty8/pokedex-origins-map`,
private). Edit `data/map_data.json` through flagkit and `app/index.html` / `app/style.css` /
`app/app.js` by hand; `python3 -I flagkit.py build` assembles `dist/`, which is what gets
published. Treat `data/` and `app/` as the current published version.

## The rules that keep this cheap

1. **Never read the artifact's HTML into the conversation to find something.** `grep -n` it in
   `app/app.js` (or `app/index.html`, `app/style.css`) and read only the lines you will change.
2. **Never dump `map_data.json`.** It is ~940 KB. Ask `flagkit.py` instead; it prints lines, not
   blobs.
3. **No screenshots for anything the data or the DOM can answer**, and never a second screenshot
   of the same screen. Most flags are settled by `flagkit.py show` plus the page source.
4. **One batch write at the end**, not a write per flag.
5. A `map_data.json` edit lives only in the published JSON and is overwritten whenever the
   dataset is regenerated (`meta.build`) — say so in the flag note every time, and see
   "Surviving a rebuild". **Geography is different:** a pin belongs in `data/geo_hand.json`,
   which the generator reads as its strongest source, so it survives. Never hand-edit a pin
   into `data/geo.json`; that file is generated output.

## Loop

### 1. Read the open flags

```
ArtifactData action=query url=<artifact> collection=corrections
  query={"where": [["status", "ne", "done"]], "limit": 50}
```

Each doc: `targetType` (`referent` | `group` | `node` | `species` | `place`), `target`, `label`,
`issue`, `suggestion`, `note`, `status`. `node` covers a category, branch, family or region — the
page files all four under that one type. `place` is a pin on the Atlas tab, and its target is the
place name as `data/geo.json` spells it. Fix geography in `data/geo_hand.json` and re-run
`python3 -I tools/geobuild.py`, never in `map_data.json` and never in `data/geo.json` itself:

```json
{"place":   {"<referent>": {"place":"Mongolia","lat":46.0,"lon":105.0,"q":"Q711","why":"..."}},
 "unplace": {"<referent>": "why it is from nowhere"}}
```

`place` pins a referent and `unplace` suppresses whatever the passes found; `why` is shown on
the card, so write it for a reader. Use a place name and coordinates that already appear in
`data/geo.json` so one place keeps one pin, and omit `q` for one of our own culture areas —
the card then reads it as an area rather than a spot. If a hop put the referent somewhere
absurd, fix the hop in `tools/geodeep.py` (`BROAD`, `SCRIPTISH`, and the rule that refuses a
parent naming several places) rather than papering over it here.

### 2. Refresh the working copies if the session is new

```
Artifact action=read url=<artifact> paths=["map_data.json","index.html"] out_dir=<this skill>/work
```

Save the dataset over `data/map_data.json` (run `flagkit build` after). Compare `meta.build`
with what the flag notes mention:
a flag applied under an older build may have been regenerated away.

### 3. Diagnose each flag — data or page?

```bash
python3 -I flagkit.py show "<target>"        # referent / cluster / family, counts and all
python3 -I flagkit.py species "<target>"     # the Pokémon under it, with form-sprite overrides
python3 -I flagkit.py where Ponyta           # which referents and clusters a Pokémon hangs off
python3 -I flagkit.py grep aspen             # find the real spelling
```

- The numbers are wrong, something sits in the wrong family, two clusters should be one → **data**.
- The number is right but the panel or the map does not show it → **page**. Find the code with
  `grep -n` in `app/app.js`; the render paths are `renderDetail` (side panel), `drawGraph`
  (map), `drawAtlas`/`atlasPlaces` (the Atlas tab), `groupNode`/`childrenOf` (what is openable),
  `render` (lists).
- A flag can be neither: Bulbapedia may simply say what the page says. Then reply, do not patch.

### 4. Fix

Data — these recompute every count and refuse to save if integrity breaks:

```bash
python3 -I flagkit.py move-family "mudskipper" "Fish"
python3 -I flagkit.py nest "zebra foal" "zebra"
python3 -I flagkit.py unnest "<cluster>"
python3 -I flagkit.py merge "<from-cluster>" "<into-cluster>"
python3 -I flagkit.py set-kind "<referent-or-cluster>" "<kind>"
python3 -I flagkit.py regroup "<new>" "<parent-or-family>" "<cluster>"...
python3 -I flagkit.py rename "<old cluster>" "<new cluster>"
python3 -I flagkit.py split-family "<old>" "<new>" "<top-level cluster>"...
python3 -I flagkit.py rename-family "<old>" "<new>"
python3 -I flagkit.py merge-ref "<from referent>" "<into referent>"
python3 -I flagkit.py check                  # always ends clean before you publish
```

Add `--dry` to see the summary without saving. For an edit flagkit has no command for, patch
`data/map_data.json` with a short python heredoc and then run `check` — it catches stale `tn`,
stale family `n`, `leaf` flags that disagree with the referent count, orphans and double parents.

Page — edit the file in `app/` with a python heredoc (exact-match replace, assert the
count is 1), keeping the file's own comment voice.

### 5. Publish

```bash
python3 -I tests/test_flagkit.py && python3 -I flagkit.py build
```

```
Artifact url=<artifact> file_path=<this skill>/dist/index.html
         files={"style.css": ".../dist/style.css", "app.js": ".../dist/app.js",
                "map_data.json": ".../dist/map_data.json",
                "world.json": ".../dist/world.json", "geo.json": ".../dist/geo.json"}
```

Pass every file whose content changed; files left out keep their published version, which is
how `sprites.json` and `form_sprites.json` survive without being in the repo. If another writer published in between, the call is
refused and hands back a diff — merge it into the file in `app/` and publish again. A publish that
is refused as "identical content resent" goes through on a straight retry.

### 6. Commit what changed

The repo is `ashetty8/pokedex-origins-map` (private), checked out at this skill's own
directory. After publishing, record the same change in git — the overlay's diff is the
readable account of what moved:

```bash
git add -A && git commit -m "<what changed, and the version id>" && git push
```

`data/map_data.json` diffs show the correction itself, so the commit is the record; there is
no separate overlay file to keep in step.

### 7. Mark them applied, in one call

```
ArtifactData action=batch url=<artifact> writes=[
  {"op":"update","collection":"corrections","doc_id":"<id>","if_version":<version>,
   "data":{"status":"done","note":"Applied in <version id>: <what changed, in one or two lines>."}},
  …]
```

`if_version` is the `version` from the read in step 1. Note what changed and why, name the
version, and for a `map_data.json` edit add that the generator will revert it. A geography fix
made in `data/geo_hand.json` survives a rebuild, so do not claim otherwise.

## Verifying without burning tokens

Order of preference:

1. **The data answers it** — `flagkit.py show` after the edit. Enough for every data flag.
2. **The page's own output as text.** The published page runs cross-origin inside claude.ai, so
   `read_page` and `javascript_tool` cannot reach it. Serve `dist/` locally instead:
   write `.claude/launch.json` with
   `{"version":"0.0.1","configurations":[{"name":"verify-pokedex","runtimeExecutable":"python3","runtimeArgs":["-m","http.server","8732","--directory","<this skill>/dist"],"port":8732}]}`,
   run `flagkit build` first, fetch `sprites.json` / `form_sprites.json` into `dist/` only if
   the flag is about sprites, then `preview_start` by
   name and read with `get_page_text` / `find`. Delete the launch.json afterwards. Running a
   server straight from Bash is blocked; this is the route that works.
3. **One screenshot**, only for something genuinely visual — overlapping labels, a wrong sprite,
   a badge that should appear. On the live artifact you must drive by coordinates, since the
   frame is cross-origin. One is the budget.

## Surviving a rebuild

Every data edit lives only in the published JSON; the file still reports the generator's
`meta.build`, and a regeneration wipes all of it. So after any data change:

```bash
python3 -I flagkit.py patch apply <fresh map_data.json>
```

It reads the structure straight off `data/map_data.json` — where everything sits, never the
derived counts — and replays it onto the new build.

It recreates missing families and the grouping clusters this work invented, refiles referents,
rebuilds every family listing and count from the result, runs the integrity check, and writes
`<fresh>.patched.json`. It never deletes: it reports what the overlay knows but the build
lacks, and what the build has but the overlay does not — the second list is where merged-away
duplicates reappear, so re-merge those by hand and export again.

## What the dataset means

- `groups` — clusters. `m` own referents, `ch` child clusters, `p` parent, `f` family,
  `n` Pokémon from own referents, `tn` Pokémon in the whole subtree, `leaf: 1` when it has a
  single own referent (children do not affect it; the page recomputes leafness itself).
- `families` — `c` lists multi-referent clusters, `l` single-referent leaves, `n` Pokémon under
  the family, `b` its branch. Only un-nested clusters are listed.
- `referents` — `s` species ids, `g` its cluster, `k` category, `w` Wikipedia title, `i: 1`
  category inferred, `x: 1` an allusion rather than a design source.
- `formrefs[referent][species] = form slug` — the referent is about one *form*, so that form's
  sprite is the right face (`shetland pony` → `ponyta-galar`).
- `branches` — `kind → [[branch name, [families]]]`. A branch holding one family collapses.
