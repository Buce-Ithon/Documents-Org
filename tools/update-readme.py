#!/usr/bin/env python3
"""Keep the per-directory org file lists in README.md in sync with the files on disk.

Rules
-----
* Each ``## Section`` in the README maps to a directory of the same name
  (case-insensitive). ``Daily life management`` always maps to the repository
  root. Sections without a matching directory (e.g. Technical content) are
  left untouched.
* Every top-level directory holding org files gets a ``##`` section of its own,
  created on demand and inserted right after the root section, sorted by name.
  A section whose directory has become empty keeps its heading but loses its
  list.
* Files are sorted oldest to newest by the time of their last git commit;
  untracked files fall back to their file modification time (pass ``--mtime``
  to sort purely by modification time).
* Directories below the top level are expanded recursively as ``###``
  headings, with sibling directories ordered by name.
* Only the regions between ``<!-- ORG-LIST:START/END -->`` and
  ``<!-- ORG-INDEX:START/END -->`` are rewritten; missing markers are inserted
  automatically, taking over the old link lines that follow a heading.

Usage
-----
    python tools/update-readme.py           # update README.md in place
    python tools/update-readme.py --check   # check only, exit code 1 when stale
    python tools/update-readme.py --mtime   # sort by file modification time
    python tools/update-readme.py --dry-run # print the result, do not write
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

LIST_START = "<!-- ORG-LIST:START -->"
LIST_END = "<!-- ORG-LIST:END -->"
INDEX_START = "<!-- ORG-INDEX:START -->"
INDEX_END = "<!-- ORG-INDEX:END -->"

ROOT_SECTION = "Daily life management"
NO_INDEX = {"contents", "disclaimer"}

H1 = re.compile(r"^# +(.+?)[ \t]*\n", re.M)
H2 = re.compile(r"^## +(.+?)[ \t]*\n", re.M)
SPECIAL = set(" ()<>[]\\")

_git_cache: dict[str, float | None] = {}


# ---------------------------------------------------------------- 时间戳

def git_ctime(rel: str) -> float | None:
    """文件最后一次提交的时间；未跟踪/无提交时返回 None。"""
    if rel not in _git_cache:
        try:
            out = subprocess.run(
                ["git", "-C", str(ROOT), "log", "-1", "--format=%ct", "--", rel],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            stamp = out.stdout.strip()
            _git_cache[rel] = float(stamp) if out.returncode == 0 and stamp.isdigit() else None
        except OSError:
            _git_cache[rel] = None
    return _git_cache[rel]


def sort_key(path: Path, use_mtime: bool):
    """排序键：默认用最后一次提交时间，未提交的文件退回修改时间。"""
    rel = path.relative_to(ROOT).as_posix()
    stamp = path.stat().st_mtime if use_mtime else git_ctime(rel)
    if stamp is None:
        stamp = path.stat().st_mtime
    return (stamp, path.name.lower())


# ---------------------------------------------------------------- 渲染

def link_line(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    # 链接文本里的方括号一律转义：CommonMark 渲染结果不变，但 Emacs 的
    # markdown-mode 用的正则是非嵌套的（组 3 为 \([^]]\)*），裸括号会让整条链接
    # 匹配不上，标记折叠（markdown-toggle-markup-hiding）也就失效。
    label = rel.replace("[", r"\[").replace("]", r"\]")
    target = f"<./{rel}>" if SPECIAL & set(rel) else f"./{rel}"
    return f"[{label}]({target})"


def render_dir(directory: Path, level: int, use_mtime: bool, claimed: set[Path]) -> str:
    """递归渲染一个目录：先列文件（按时间），再列子目录（按名称）。

    ``claimed`` 中的目录已被其它 ``##`` 小节收录，不再作为子标题展开。
    """
    entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    files = [p for p in entries if p.is_file() and p.suffix.lower() == ".org"]
    subdirs = [p for p in entries
               if p.is_dir() and not p.name.startswith(".") and p.resolve() not in claimed]

    blocks: list[str] = []
    if files:
        files.sort(key=lambda p: sort_key(p, use_mtime))
        blocks.append("\n".join(link_line(p) for p in files))
    for sub in subdirs:
        body = render_dir(sub, level + 1, use_mtime, claimed)
        if body:
            hashes = "#" * min(level + 1, 6)
            blocks.append(f"{hashes} {sub.name}\n\n{body}")
    return "\n\n".join(blocks)


def anchor(title: str) -> str:
    return "#" + title.replace(" ", "-")


# ---------------------------------------------------------------- 结构解析

def resolve_dir(title: str) -> Path | None:
    if title.casefold() == ROOT_SECTION.casefold():
        return ROOT
    for child in ROOT.iterdir():
        if child.is_dir() and not child.name.startswith(".") and child.name.casefold() == title.casefold():
            return child
    return None


def section_spans(text: str):
    """返回 [(title, heading_start, heading_end)]，按出现顺序。"""
    return [(m.group(1), m.start(), m.end()) for m in H2.finditer(text)]


def next_heading(text: str, pos: int) -> int:
    m = H2.search(text, pos)
    return m.start() if m else len(text)


def find_block(text: str, lo: int, hi: int) -> tuple[int, int] | None:
    start = text.find(LIST_START, lo, hi)
    if start == -1:
        return None
    end = text.find(LIST_END, start, hi)
    if end == -1:
        return None
    return start, end + len(LIST_END)


def is_entry_line(line: str) -> bool:
    line = line.strip()
    if line.startswith("- "):
        line = line[2:].strip()
    return line.startswith("[") and line.endswith(")")


def bootstrap_span(text: str, start: int, hi: int) -> tuple[int, int]:
    """没有标记时，接管 start 之后紧跟的空行与旧条目行。

    只吃到最后一个条目行为止，尾部的空行原样保留，避免挤压小节间的间距。
    """
    pos = end = start
    while pos < hi:
        nl = text.find("\n", pos, hi)
        line = text[pos:hi if nl == -1 else nl]
        if line.strip() == "" or is_entry_line(line):
            if is_entry_line(line):
                end = hi if nl == -1 else nl + 1
            if nl == -1:
                break
            pos = nl + 1
        else:
            break
    return start, end


# ---------------------------------------------------------------- 主流程

def sub_headings(body: str) -> list[str]:
    """返回渲染结果里所有 ``###`` 子标题，供目录索引使用。"""
    return [m.group(1) for m in re.finditer(r"^### +(.+?)[ \t]*$", body, re.M)]


def top_level_dirs() -> list[Path]:
    """仓库根目录下含 org 文件的直接子目录，按名称排序。"""
    found = []
    for child in sorted(ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if any(child.rglob("*.org")):
            found.append(child)
    return found


def remove_block_span(text: str, start: int, end: int) -> tuple[int, int]:
    """清空托管区段时，把它两侧的空行各收掉一个，免得留下连续空行。"""
    if start >= 2 and text[start - 1] == "\n" and text[start - 2] == "\n":
        start -= 1
    if text[end : end + 2] == "\n\n":
        end += 1
    return start, end


def insert_after_root(text: str, payload: str) -> str:
    """把新增的小节插到根目录小节之后；找不到根目录小节时追加到文末。"""
    for title, _, hend in section_spans(text):
        if title.casefold() != ROOT_SECTION.casefold():
            continue
        block = find_block(text, hend, next_heading(text, hend))
        if block:
            return text[: block[1]] + "\n\n" + payload + text[block[1]:]
        # 标题后面没有托管区段：按后面的实际情况补足空行，避免多出空行
        rest = text[hend:]
        if not rest.strip():
            return text[:hend] + "\n" + payload + "\n"
        gap = rest if rest.startswith("\n\n") else ("\n" + rest if rest.startswith("\n") else "\n\n" + rest)
        return text[:hend] + "\n" + payload + gap
    return text.rstrip("\n") + "\n\n" + payload + "\n"


def rewrite(text: str, use_mtime: bool) -> tuple[str, list[str]]:
    warnings: list[str] = []
    spans = section_spans(text)
    edits: list[tuple[int, int, str]] = []
    index_entries: list[str] = []
    section_dirs = {title: resolve_dir(title) for title, _, _ in spans}
    claimed_set = {d.resolve() for d in section_dirs.values() if d is not None}

    # 没有同名小节的顶层目录：一律升格成同级 ## 小节，而不是塞进根目录小节里。
    new_dirs = [d for d in top_level_dirs() if d.resolve() not in claimed_set]
    claimed_set |= {d.resolve() for d in new_dirs}
    new_bodies = {d: render_dir(d, 2, use_mtime, claimed_set) for d in new_dirs}
    new_bodies = {d: b for d, b in new_bodies.items() if b}

    new_index: list[str] = []
    for d in new_bodies:
        new_index.append(f"- [{d.name}]({anchor(d.name)})")
        new_index.extend(f"  - [{h}]({anchor(h)})" for h in sub_headings(new_bodies[d]))

    for i, (title, _, hend) in enumerate(spans):
        hi = spans[i + 1][1] if i + 1 < len(spans) else len(text)
        if title.casefold() in NO_INDEX:
            continue

        index_entries.append(f"- [{title}]({anchor(title)})")

        directory = section_dirs[title]
        if directory is None:
            # 目录被改名或删除了：清掉遗留的死链接，标题留给你决定去留。
            span = find_block(text, hend, hi)
            if span:
                edits.append((*remove_block_span(text, *span), ""))
                warnings.append(
                    f"section `{title}` has no matching directory; its list was cleared "
                    "(delete the section if you no longer need it)"
                )
            continue

        if directory.resolve() == ROOT.resolve():
            index_entries.extend(new_index)

        body = render_dir(directory, 2, use_mtime, claimed_set)
        block = f"{LIST_START}\n{body}\n{LIST_END}"
        span = find_block(text, hend, hi)

        if not body:
            # 目录已无 org 文件：保留标题，清空清单。
            if span:
                edits.append((*remove_block_span(text, *span), ""))
            continue

        edits.append((*span, block) if span else (*bootstrap_span(text, hend, hi), "\n" + block + "\n"))
        index_entries.extend(f"  - [{h}]({anchor(h)})" for h in sub_headings(body))

    # 没有根目录小节时，新小节排在索引最前面
    if new_index and not any(d and d.resolve() == ROOT.resolve() for d in section_dirs.values()):
        index_entries = new_index + index_entries

    # 目录索引
    h1 = next((m for m in H1.finditer(text) if m.group(1).casefold() == "contents"), None)
    if h1 is not None:
        hi = next((s[1] for s in spans if s[1] > h1.end()), len(text))
        block = f"{INDEX_START}\n" + "\n".join(index_entries) + f"\n{INDEX_END}"
        span = find_block_index(text, h1.end(), hi)
        edits.append((*span, block) if span else (*bootstrap_span(text, h1.end(), hi), "\n" + block + "\n"))
    elif index_entries:
        warnings.append("no `# Contents` section in README.md; skipping index generation")

    for start, end, new in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + new + text[end:]

    if new_bodies:
        payload = "\n\n".join(
            f"## {d.name}\n\n{LIST_START}\n{body}\n{LIST_END}" for d, body in new_bodies.items()
        )
        text = insert_after_root(text, payload)

    return text, warnings


def find_block_index(text: str, lo: int, hi: int) -> tuple[int, int] | None:
    start = text.find(INDEX_START, lo, hi)
    if start == -1:
        return None
    end = text.find(INDEX_END, start, hi)
    if end == -1:
        return None
    return start, end + len(INDEX_END)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the org file lists in README.md.")
    parser.add_argument("--check", action="store_true", help="check only; exit code 1 when the README is stale")
    parser.add_argument("--dry-run", action="store_true", help="print the result instead of writing it")
    parser.add_argument("--mtime", action="store_true", help="sort by file modification time (default: last commit time)")
    parser.add_argument("--git", action="store_true", help=argparse.SUPPRESS)  # deprecated, kept for compatibility
    args = parser.parse_args()

    original = README.read_text(encoding="utf-8")
    updated, warnings = rewrite(original, args.mtime)

    for message in warnings:
        print(f"warning: {message}", file=sys.stderr)

    if updated == original:
        print("README.md is up to date")
        return 0

    if args.dry_run:
        sys.stdout.write(updated)
        return 0

    if args.check:
        print("README.md is out of sync with the org files on disk; run python tools/update-readme.py", file=sys.stderr)
        return 1

    tmp = README.with_suffix(".md.tmp")
    tmp.write_text(updated, encoding="utf-8", newline="\n")
    os.replace(tmp, README)
    print("README.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
