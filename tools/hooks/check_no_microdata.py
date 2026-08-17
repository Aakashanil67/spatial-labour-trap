"""Refuse to commit anything that looks like DataFirst microdata.

.gitignore stops an accidental `git add`, not a deliberate `git add -f`. This runs as a
pre-commit hook so the block survives -f, and it checks paths AND magic bytes, so a QLFS
extract renamed away from .dta is still caught -- for the Stata/SPSS binary formats this
project actually receives files in. See D9 in DECISIONS.md.

**What this does NOT catch, stated plainly rather than implied by the docstring above's old,
overclaiming version: microdata re-exported as plain CSV or another text format has no reliable
binary signature to detect** -- a renamed QLFS extract saved as CSV looks like any other CSV to
this hook. The safeguard for that case is the `raw/` path check plus this project's own
discipline (never export microdata to a working file outside `data/raw/`, never paste a row of
it into a prompt -- see data/README.md), not automated content detection. Treat "never commit
microdata" as a project rule this hook partially automates, not a guarantee it enforces alone.

Every restriction referenced here is this project's own policy, not a claim about what CC-BY
itself forbids: DataFirst's QLFS/PALMS/NIDS-W5/NHTS catalogue entries carry a CC-BY licence,
which is permissive by design (see data/README.md's "What the DataFirst licence permits
publishing here") -- the restriction on redistributing individual-level records comes from
DataFirst's own microdata access terms, a separate thing from the CC-BY tag on the aggregate
catalogue entry, and this project chooses never to commit microdata regardless of licence tier.
"""

import subprocess
import sys
from pathlib import Path

BLOCKED_EXTENSIONS = {".dta", ".sav", ".por", ".zip"}
BLOCKED_PATH_PARTS = {"raw"}

# Newer Stata (.dta format 117+) and SPSS .sav both carry a human-readable magic string.
MAGIC_PREFIXES = [b"<stata_dta>", b"$FL2", b"\x24\x46\x4c\x32"]

# Stata .dta format <= 115 (Stata 6 through 12 -- what QLFS/NHTS/PALMS actually ship as, e.g.
# QLFS's own files here are format 113) has no human-readable magic string, just a 4-byte
# header: a release-number byte, a byteorder byte, a filetype byte that must be 1, and an
# unused zero byte. Requiring all four fields together keeps the false-positive rate on
# arbitrary binary files negligible -- confirmed against the real QLFS/NHTS files on disk
# during this check's own testing, both format 113.
_OLD_STATA_RELEASE_BYTES = {102, 103, 104, 105, 108, 109, 110, 111, 112, 113, 114, 115}


def _looks_like_old_stata_header(head: bytes) -> bool:
    if len(head) < 4:
        return False
    release, byteorder, filetype, unused = head[0], head[1], head[2], head[3]
    return (
        release in _OLD_STATA_RELEASE_BYTES
        and byteorder in (1, 2)
        and filetype == 1
        and unused == 0
    )


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
        if _looks_like_old_stata_header(head):
            return "file content matches an old-format (Stata <= 12) .dta header"
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
            "\nThis project's own policy is to never commit individual-level microdata from "
            "NIDS/QLFS/PALMS/NHTS, regardless of the permissive CC-BY tag on DataFirst's "
            "aggregate catalogue entries -- see data/README.md. If this is a false positive "
            "(e.g. a genuinely public results file that happens to end in .zip), rename it or "
            "move it out of a raw/ directory."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
