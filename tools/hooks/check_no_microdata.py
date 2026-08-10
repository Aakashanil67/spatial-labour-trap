"""Refuse to commit anything that looks like DataFirst microdata.

.gitignore stops an accidental `git add`, not a deliberate `git add -f`. This runs as a
pre-commit hook so the block survives -f, and it checks paths AND magic bytes, because a
QLFS extract renamed to results.csv should still be caught. See D9 in DECISIONS.md.
"""

import subprocess
import sys
from pathlib import Path

BLOCKED_EXTENSIONS = {".dta", ".sav", ".por", ".zip"}
BLOCKED_PATH_PARTS = {"raw"}

# Stata .dta: 'Ll' or '<stata_dta>' header depending on version. SPSS .sav: '$FL2' magic.
MAGIC_PREFIXES = [b"<stata_dta>", b"$FL2", b"\x24\x46\x4c\x32"]


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def looks_like_microdata(path: Path) -> str | None:
    if path.suffix.lower() in BLOCKED_EXTENSIONS:
        return f"blocked extension {path.suffix}"
    if BLOCKED_PATH_PARTS & set(path.parts):
        return "path contains a raw/ data directory"
    if path.exists() and path.is_file():
        try:
            head = path.read_bytes()[:16]
        except OSError:
            return None
        if any(head.startswith(m) for m in MAGIC_PREFIXES):
            return "file content matches a Stata/SPSS data file signature"
    return None


def main() -> int:
    offenders = []
    for name in staged_files():
        reason = looks_like_microdata(Path(name))
        if reason:
            offenders.append((name, reason))

    if offenders:
        print("BLOCKED: staged file(s) look like restricted survey microdata:\n")
        for name, reason in offenders:
            print(f"  {name}  ({reason})")
        print(
            "\nThe DataFirst licence for NIDS/QLFS/PALMS/NHTS forbids redistributing raw "
            "microdata. If this is a false positive (e.g. a genuinely public results file "
            "that happens to end in .zip), rename it or move it out of a raw/ directory."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
