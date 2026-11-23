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
| `## Arrangement` | `Arrangement/` |
| `## Language learning` | `Language learning/` |
| `## Software use` | `Software Use/` |
| `## Technical content` | no such directory yet → left untouched |

A section that never had a list (such as `## Technical content`) is left completely untouched. One whose directory has disappeared keeps its heading, but its now-dead list is cleared and a warning is printed:

```
warning: section `Programming` has no matching directory; its list was cleared
```

**Top-level directories are never nested.** Every direct subdirectory of the repository root that contains org files gets its own `##` section, whether or not the heading already exists:

- If the heading is missing, it is created automatically, together with its managed block and its `# Contents` entry.
- New sections are inserted directly after the root section (`## Daily life management`), ordered by directory name. Sections that already exist are left where they are.
- A directory whose section exists but which no longer holds any org files keeps its heading; only the list inside is cleared.

Adding a category therefore needs no script change at all: create the directory, drop in org files, run the script.

### Ordering

Files are sorted from oldest to newest by the time of their **last git commit**; entries sharing a timestamp are ordered by file name.

- Untracked files have no commit time and fall back to the file modification time, so a freshly written file always lands at the end.
- Commit time only changes once you commit: editing a file without committing leaves its position alone.
- Pass `--mtime` to sort by file modification time instead.

> Why commit time rather than mtime: git does not store mtimes, so a fresh clone gives every file the checkout timestamp and mtime ordering collapses into filename ordering.

### Subdirectories

Directories *below* the top level are expanded recursively as `###`, `####` headings, with sibling directories ordered by name. For example `Language learning/Daily expression/` becomes a `### Daily expression` subsection inside `## Language learning`.

The root section only ever lists files sitting directly in the repository root, and a directory claimed by its own `##` section is never expanded a second time under its parent.

### Link escaping

Square brackets in a file name are backslash-escaped inside the link text:

```markdown
[Programming/cpp-a-little-from-entt-stl-functional\[explanation\].org](<./Programming/cpp-a-little-from-entt-stl-functional[explanation].org>)
```

CommonMark renders this exactly like the unescaped form, so GitHub and friends are unaffected. Emacs users need it: markdown-mode matches inline links with a non-nesting regex, where an unescaped `]` terminates the link text early and the whole link then fails to fontify — so `markdown-toggle-markup-hiding` silently leaves the line unfolded.

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

## Inspecting the setup

Coming back to the repository after a long break? Run:

```powershell
pwsh tools/doctor.ps1
```

It prints the hooks directory git is actually using, the hooks that live there (i.e. the ones that are active), the configured git aliases, and whether `README.md` is still in sync.

The same information by hand:

| Question | Command |
|---|---|
| Is `core.hooksPath` set? | `git config --show-origin --get core.hooksPath` (exit code 1 = unset) |
| Which hooks directory is in use? | `git rev-parse --git-path hooks` — respects `core.hooksPath` |
| Which hooks are active? | `Get-ChildItem (git rev-parse --git-path hooks)` — any file that is not `*.sample` |
| What hook names exist at all? | `git help githooks` |
| All config, with scope and origin | `git config --list --show-origin --show-scope` |
| Aliases only | `git config --get-regexp '^alias\.'` |
| Is the README in sync? | `python tools/update-readme.py --check` |

A hook is "enabled" purely by the presence of a file of that name in the hooks directory — there is no separate on/off switch. Deleting the file, or unsetting `core.hooksPath`, disables it.

## Troubleshooting

**Wrong order / new file is not at the end**: the file has not been committed yet. Run `git add` and `git commit`, then run the script again.

**Saving an old file in Emacs changed the order**: that affects `--mtime` mode only; the default commit-time mode is unaffected.

**git is unavailable**: every file falls back to mtime. The script still works, it just cannot query commit times.

**I want to edit the list by hand**: edit outside the marker regions, or edit and re-run the script — whatever sits inside the markers will be overwritten.
