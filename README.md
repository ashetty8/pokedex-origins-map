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
| `dist/` | What gets published: the three app files plus a minified `map_data.json`. Rebuilt by `flagkit build`, never edited. |
| `flagkit.py` | Inspect and edit the dataset safely: every write recomputes counts and refuses to save if integrity breaks. |
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

`map_data.json` carries a `meta.build` from the generator that produced it. Every correction
applied here lives only in the published JSON, so a regeneration erases all of it. The overlay
is the insurance:

```bash
python3 -I flagkit.py patch export            # snapshot the structure
python3 -I flagkit.py patch apply <fresh.json>  # replay it onto a new build
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

Origin text is from [Bulbapedia](https://bulbapedia.bulbagarden.net) (CC BY-NC-SA 2.5);
species data and sprites are from [PokéAPI](https://pokeapi.co). Pokémon is © Nintendo /
Creatures Inc. / GAME FREAK Inc. This is a non-commercial fan project — keep the repository
private unless you have checked what those terms allow.
