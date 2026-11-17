# Pokédex Origins Map

What Bulbapedia says each Pokémon was drawn from, as a browsable map: 1,025 Pokémon,
~3,900 referents, ~2,600 clusters, 59 families, in ten categories.

Published as a private Claude Artifact: https://claude.ai/artifact/FP9NhVBPPv8ozSKYAfhBR8

## What is in here

| Path | What it is |
|---|---|
| `work/page.html` | The whole application — one file, no build step. Published as the artifact's page. |
| `work/map_data.json` | The dataset the page fetches. Generated upstream, then hand-corrected (see below). |
| `work/overlay.json` | The hand-made structure, replayable onto a fresh generated dataset. |
| `flagkit.py` | Inspect and edit the dataset safely: every write recomputes counts and refuses to save if integrity breaks. |
| `SKILL.md` | The working loop: read flags, diagnose, fix, publish, mark applied. |

`sprites.json` and `form_sprites.json` (~2 MB of base64 PNGs) are published alongside the page
but are not kept here; fetch them from the artifact when a sprite question comes up.

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
