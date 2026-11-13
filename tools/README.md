# update-readme

Keeps the per-directory org file lists in the repository's [README.md](../README.md) up to date, so they no longer have to be edited and re-sorted by hand.

## Files

| File | Purpose |
|---|---|
| `update-readme.py` | Main script: scans `*.org` on disk and rewrites the README |
| `update-readme.el` | Emacs wrapper providing `M-x update-readme` / `M-x update-readme-check` |
| `../.githooks/pre-commit` | Optional hook that syncs the README before each commit (disabled by default) |

## Usage

```powershell
python tools/update-readme.py           # update README.md in place
python tools/update-readme.py --check   # check only, exit code 1 when out of sync
python tools/update-readme.py --dry-run # print the result instead of writing it
python tools/update-readme.py --mtime   # sort by file modification time instead
```

In Emacs:

```elisp
(load-file "~/Documents/Org/tools/update-readme.el")
;; M-x update-readme        — update, and refresh an already open README buffer
;; M-x update-readme-check  — check only
```

Adjust `update-readme-python` if Python is not on the default path, and `update-readme-script` if the script lives elsewhere.

## How it works

### Sections map to directories

Each `## Section` in the README maps to a directory of the same name, case-insensitively:

| README section | Directory |
|---|---|
| `## Daily life management` | repository root (fixed, see `ROOT_SECTION`) |
| `## Language learning` | `Language learning/` |
| `## Software use` | `Software Use/` |
| `## Technical content` | no such directory yet → left untouched |

Adding a new category therefore needs no script change: create a `Technical content/` directory, add a `## Technical content` section to the README, and run the script again — both the file list and the `# Contents` index are filled in automatically.

Conversely, if a directory already holds org files but has no matching `##` section, the script prints a warning to stderr rather than dropping it silently:

```
warning: directory `Misc/papers` contains org files but no matching `##` section in README.md
```

### Ordering

Files are sorted from oldest to newest by the time of their **last git commit**; entries sharing a timestamp are ordered by file name.

- Untracked files have no commit time and fall back to the file modification time, so a freshly written file always lands at the end.
- Commit time only changes once you commit: editing a file without committing leaves its position alone.
- Pass `--mtime` to sort by file modification time instead.

> Why commit time rather than mtime: git does not store mtimes, so a fresh clone gives every file the checkout timestamp and mtime ordering collapses into filename ordering.

### Subdirectories

Subdirectories are expanded recursively as `###`, `####` headings, with sibling directories ordered by name.

A directory already claimed by another `##` section is not expanded a second time under its parent — the root section, for instance, does not list `Language learning/` or `Software Use/` again.

### Managed regions

The script only rewrites the content between these markers:

```markdown
<!-- ORG-LIST:START -->
...
<!-- ORG-LIST:END -->
```

```markdown
<!-- ORG-INDEX:START -->
...
<!-- ORG-INDEX:END -->
```

There is one `ORG-LIST` block per directory section, and a single `ORG-INDEX` block for the `# Contents` list. Everything else — Description, Disclaimer, `This section is not yet complete.`, and so on — is left alone.

Missing markers are inserted automatically, taking over the old link lines that directly follow a heading, so an existing README can be migrated in one run.

## Optional: sync before commit

```powershell
git config core.hooksPath .githooks   # enable (this repository only)
git config --unset core.hooksPath     # disable
```

Once enabled, every `git commit` runs the script first; if the README changed, it is `git add`-ed and included in that commit.

Without `--global` or `--system`, `core.hooksPath` is written to `.git/config`, so it applies only to the repository where it was set. Other repositories are unaffected unless you have set it in your global config too. Confirm the origin with `git config --show-origin core.hooksPath` — it should read `file:.git/config`.

## Troubleshooting

**Wrong order / new file is not at the end**: the file has not been committed yet. Run `git add` and `git commit`, then run the script again.

**Saving an old file in Emacs changed the order**: that affects `--mtime` mode only; the default commit-time mode is unaffected.

**git is unavailable**: every file falls back to mtime. The script still works, it just cannot query commit times.

**I want to edit the list by hand**: edit outside the marker regions, or edit and re-run the script — whatever sits inside the markers will be overwritten.
