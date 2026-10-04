"""Pre-upload review of the staged repository.

Checks the things that actually break a published repo:
  1. build junk (.pyc / __pycache__) staged for upload;
  2. broken relative links inside the markdown;
  3. machine-specific absolute paths leaked into committed text;
  4. files that are not valid UTF-8, or lack a trailing newline;
  5. repo-name consistency across README, pyproject and the clone URL;
  6. the skills each carry their internals layer;
  7. the example's artifacts are all present.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
REPO_NAME = "dsh-chatgpt-bridge"
REPO_URL = f"https://github.com/Jxbbbbbyan/{REPO_NAME}"

problems: list[str] = []
notes: list[str] = []


def check_junk() -> None:
    junk = [p for p in REPO.rglob("*") if p.is_dir() and p.name == "__pycache__"]
    for directory in junk:
        shutil.rmtree(directory)
        notes.append(f"removed build junk: {directory.relative_to(REPO)}")
    for path in REPO.rglob("*.pyc"):
        path.unlink()
        notes.append(f"removed build junk: {path.relative_to(REPO)}")


def markdown_files() -> list[Path]:
    return [p for p in REPO.rglob("*.md") if p.is_file()]


def check_links() -> None:
    pattern = re.compile(r"\]\(([^)\s]+)\)")
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            resolved = (path.parent / clean).resolve()
            if not resolved.exists():
                problems.append(f"broken link in {path.relative_to(REPO)}: {target}")


def check_absolute_paths() -> None:
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix in {".png", ".jpg", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"not valid UTF-8: {path.relative_to(REPO)}")
            continue
        for pattern in (r"C:\\Users\\Admin", r"C:\\Program Files", r"D:\\miniconda3"):
            if pattern.replace("\\\\", "\\") in text:
                problems.append(f"machine path leaked in {path.relative_to(REPO)}: {pattern}")


def check_encoding_and_newline() -> None:
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix in {".png", ".jpg", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"not valid UTF-8: {path.relative_to(REPO)}")
            continue
        if not text.endswith("\n"):
            problems.append(f"no trailing newline: {path.relative_to(REPO)}")


def check_naming() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    if REPO_URL not in readme:
        problems.append(f"README does not carry the clone URL {REPO_URL}")
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    if 'name = "dsh-chatgpt-bridge"' not in pyproject:
        problems.append("pyproject package name mismatch")
    for name in ("README.zh.md", "README.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        if not text.startswith(f"# {REPO_NAME}"):
            problems.append(f"{name} does not start with '# {REPO_NAME}'")


def check_skills() -> None:
    for skill in sorted((REPO / "skills").iterdir()):
        path = skill / "SKILL.md"
        if not path.is_file():
            problems.append(f"skill missing SKILL.md: {skill.name}")
            continue
        text = path.read_text(encoding="utf-8")
        if "## Toolchain internals" not in text:
            problems.append(f"skill lacks the internals layer: {skill.name}")
        if not text.startswith("---\nname: "):
            problems.append(f"skill frontmatter malformed: {skill.name}")
        if f"name: {skill.name}" not in text.split("---")[1]:
            problems.append(f"skill frontmatter name mismatch: {skill.name}")


def check_example() -> None:
    example = REPO / "examples" / "undergrad-rebuttal"
    for name in ("brief.txt", "followup.txt", "essay.md", "chatgpt-transcript-raw.md"):
        if not (example / name).is_file():
            problems.append(f"example artifact missing: {name}")
    images = sorted((example / "images").glob("slice-*.png"))
    if len(images) != 6:
        problems.append(f"expected 6 slices, found {len(images)}")
    essay = (example / "essay.md")
    if essay.is_file():
        text = essay.read_text(encoding="utf-8")
        length = len(text.replace("\n", ""))
        if length < 1500:
            problems.append(f"essay shorter than the brief required: {length}")
        if "小丑" not in text:
            problems.append("essay does not contain the required callout")
        notes.append(f"essay length: {length} characters")
    transcript = example / "chatgpt-transcript-raw.md"
    if transcript.is_file():
        raw = transcript.read_text(encoding="utf-8")
        if "ChatGPT said:" not in raw:
            problems.append("raw transcript carries no assistant output")
        notes.append(f"raw transcript: {len(raw)} bytes, {raw.count('ChatGPT said:')} assistant blocks")


def main() -> int:
    check_junk()
    check_links()
    check_absolute_paths()
    check_encoding_and_newline()
    check_naming()
    check_skills()
    check_example()

    files = [p for p in REPO.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    print(f"repo: {REPO}")
    print(f"files: {len(files)}   bytes: {total:,}")
    print("\nnotable:")
    for note in notes:
        print(f"  - {note}")
    if problems:
        print(f"\nPROBLEMS ({len(problems)}):")
        for problem in problems:
            print(f"  x {problem}")
        return 1
    print("\nREVIEW PASSED — no broken links, no leaked machine paths, no build junk,")
    print("naming consistent, skills carry their internals layer, example complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
