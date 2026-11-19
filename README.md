# Pokédex Origins Map

What Bulbapedia says each Pokémon was drawn from, as a browsable map: 1,025 Pokémon,
~3,900 referents, ~2,600 clusters, 59 families, in ten categories.

Published as a private Claude Artifact: https://claude.ai/artifact/FP9NhVBPPv8ozSKYAfhBR8

## What is in here

| Path | What it is |
|---|---|
| `app/index.html` | Markup and head — 80 lines. |
| `app/style.css` | Every style the page uses. |
| `app/app.js` | The whole application: data loading, the three views, the map, the flag store. |
| `data/map_data.json` | The dataset, one key per line so corrections read as diffs. The source of truth. |
| `data/geo.json` | The atlas layer: a place table and one row per placed referent. Built, not edited. |
| `data/world.json` | Country outlines, already projected to the page's own coordinates. Built, not edited. |
| `data/geo_raw.json`, `data/geo_deep.json` | What the two Wikidata passes found, before they are merged. |
| `dist/` | What gets published: the three app files plus a minified `map_data.json`. Rebuilt by `flagkit build`, never edited. |
| `flagkit.py` | Inspect and edit the dataset safely: every write recomputes counts and refuses to save if integrity breaks. |
| `data/applied_build.json` | The generator build the corrections in `map_data.json` were made on. Guards against a rebuild silently dropping them. |
| `tests/test_flagkit.py` | Exercises every write command against a copy of the real data. No framework; run it directly. |
| `SKILL.md` | The working loop: read flags, diagnose, fix, publish, commit. |

`sprites.json` and `form_sprites.json` (~2 MB of base64 PNGs) live in the artifact only; pull
them into `dist/` when a sprite question needs a local preview.

## Publishing

```bash
python3 -I flagkit.py build        # assemble dist/
```

then publish `dist/index.html` with `style.css`, `app.js` and `map_data.json` as its files.
Editing `dist/` directly is pointless — the next build overwrites it.

## The atlas

The **Atlas** tab plots where each design came from. Nothing about it needs a
tile server or a map API: `tools/worldgen.py` pre-projects Natural Earth 110m
outlines (public domain) into plate carree path data the page draws as SVG, so
the land takes its colours from the page's own theme and works offline.

Where a referent is *from* comes from Wikidata, in two passes, merged with the
culture areas the dataset already carries:

```bash
python3 -I tools/geofetch.py     # the referent's own item: endemic to, country of origin, coordinates…
python3 -I tools/geodeep.py      # one hop out: what it is an instance of, part of, or whose culture it is
python3 -I tools/geobuild.py     # merge both with the families' own `rg` regions -> data/geo.json
python3 -I tools/worldgen.py <countries-110m.json>   # only when the outlines change
```

Both passes query the Wikidata Query Service a few hundred articles at a time
and cache in `tools/.geocache.json` / `tools/.geodeep.json`, so a stopped run
continues. Roughly 935 of 3,890 referents land somewhere — a chandelier has no
homeland, and the map says so by leaving it off rather than guessing. A pin
placed by culture area is drawn dashed, because "Celtic & British Isles" is a
region, not a coordinate.

## Checking the Wikipedia links

```bash
python3 -I tools/wikiaudit.py data/map_data.json        # inferred referents only
python3 -I tools/wikiaudit.py data/map_data.json --all  # every referent with a title
```

Asks Wikipedia for the first paragraph behind every title the dataset names and reports three
things: titles that no longer resolve, titles that land on a *disambiguation* page (a dead end
for anyone clicking through), and first sentences whose wording contradicts the category the
referent carries. It never edits anything.

Wikipedia rate-limits long sweeps, so answers are cached in `tools/.wikicache.json` and a later
run continues where the last one stopped. Read the wording mismatches with judgement: "is a
genus of dinosaur" trips the life rule, and recently extinct animals trip the prehistoric one.

## Tests

```bash
python3 -I tests/test_flagkit.py
```

14 cases: every write command, the guard rails that must refuse rather than corrupt, and the
rebuild path. Run it before publishing a data change.

## The correction loop

Readers flag mistakes from inside the page. Flags land in the artifact's `corrections`
collection, each naming a target (a referent, a cluster, a category or a Pokémon) and what
looks wrong. The loop in `SKILL.md` works through them: diagnose against the data, decide
whether it is a data error or a rendering one, fix, publish, and write back what changed.

## Hand edits and rebuilds

`map_data.json` carries a `meta.build` from the generator that produced it, and corrections
are made in that file rather than in an overlay beside it. The one thing that can undo them is
a freshly generated dataset dropped over the top: it parses, it passes `check`, and the work is
simply absent, because the evidence left with the file.

So the build the corrections sit on is recorded in `data/applied_build.json`, and `check`,
`build` and every write command refuse to run while the two disagree. Nobody has to remember;
the tool stops you.

```bash
python3 -I flagkit.py patch apply <fresh.json>  # replay the corrections onto the new build
python3 -I flagkit.py rebased                   # then record the build they now sit on
```

The replay recreates families and grouping clusters, refiles referents, rebuilds every count,
and reports two lists for a human to settle: what the overlay knows that the new build lacks,
and what the new build has that the overlay does not — merged-away duplicates reappear there.

## Checking your work

```bash
python3 -I flagkit.py check
```

Catches orphans, clusters with two parents, `p` that disagrees with a parent's child list,
family listings that name clusters filed elsewhere, regions holding clusters of another
family, stale subtree totals, stale own-referent counts, and `leaf` markers that disagree with
the referent count. It has caught several of my own mistakes; run it before publishing.

## Sources and licensing

Map outlines are [Natural Earth](https://www.naturalearthdata.com) (public domain) and the
origin geography is from [Wikidata](https://www.wikidata.org) (CC0).
Origin text is from [Bulbapedia](https://bulbapedia.bulbagarden.net) (CC BY-NC-SA 2.5);
species data and sprites are from [PokéAPI](https://pokeapi.co). Pokémon is © Nintendo /
Creatures Inc. / GAME FREAK Inc. This is a non-commercial fan project — keep the repository
private unless you have checked what those terms allow.
