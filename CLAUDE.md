# Pokédex Origins Map

A browsable map of what Bulbapedia says each Pokémon was drawn from, published as a private
Claude Artifact: `https://claude.ai/artifact/FP9NhVBPPv8ozSKYAfhBR8`.

`README.md` describes the layout. `SKILL.md` is the flag-clearing loop — read it before working
on flags, and before any change to the dataset or the page.

## Work in a worktree

**Start by calling EnterWorktree.** Several Claude sessions work on this repo at once — four were
running on 2026-11-18, and two of them were editing `app/` and `data/geo_hand.json` in the same
working tree within a minute of each other. A shared checkout means one session's `git status`
is full of another's half-finished work, and the first careless `git add -A` commits it.

Skip the worktree only for a question that reads and changes nothing.

## Committing, in a repo other sessions are writing to

- **Never `git add -A`, `git add .` or `git commit -a`.** Add the files you changed, by name.
- Run `git status` before committing and account for every modified file. A file you did not
  touch belongs to somebody else; leave it, and say so rather than committing around it.
- `dist/` is assembled from whatever is in `app/` and `data/` at that moment, so a `flagkit build`
  in a shared tree can sweep another session's work into the published bundle. Build and publish
  from a worktree, or check `git status` first.

## The expensive mistakes

1. **Never read the artifact's published HTML or JS into the conversation to find something.**
   `grep -n` the working copy in `app/` and read only the lines you will change. The published
   `app.js` is 169 KB; reading it to locate one function costs more than the whole task.
2. **Never dump `data/map_data.json`.** It is ~2 MB. Ask `python3 -I flagkit.py` instead — `show`,
   `grep`, `species`, `where`. It prints lines, not blobs.
3. **No screenshots for anything the data or the DOM can answer**, and never a second screenshot
   of the same screen.
4. `data/` and `app/` are the current published version — treat them as the source of truth, not
   as a stale copy to refresh from the artifact.

## Changing the data

Go through `flagkit.py`: every write recomputes the counts and refuses to save if integrity
breaks. `python3 -I flagkit.py` lists the commands. Always end clean:

```bash
python3 -I flagkit.py check && python3 -I tests/test_flagkit.py
```

Corrections live in `data/map_data.json` itself; the build they were made on is recorded in
`data/applied_build.json`, and `check`, `build` and every write refuse when the two disagree.
If you are stopped by that, a fresh dataset has landed on top of the corrections — replay them
with `patch apply`, then `rebased`. See "Surviving a rebuild" in `SKILL.md`.

Geography is the exception: a pin belongs in `data/geo_hand.json`, which the generator reads as
its strongest source, so it survives a rebuild. Never hand-edit `data/geo.json`; it is output.

## Writing for people

Flag notes are the whole of what a flagger hears back — spend them on the correction, not on our
build pipeline. Commit messages explain why, not what; the diff already says what.
