"""Tests for tools/hooks/check_no_microdata.py. The real check is the old-format Stata header
detector -- see DECISIONS.md, "The microdata hook's own claims outran what it actually checked"
-- confirmed here against the exact byte pattern the real QLFS/NHTS files on this machine carry
(format 113, Stata 8/9), not just a made-up header.
"""

from __future__ import annotations

from tools.hooks.check_no_microdata import looks_like_microdata


def test_blocked_extension_is_caught_regardless_of_content(tmp_path):
    path = tmp_path / "extract.dta"
    path.write_bytes(b"not actually stata data, extension is enough")
    assert looks_like_microdata(path) is not None


def test_raw_directory_is_caught_regardless_of_extension(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    path = raw_dir / "extract.csv"
    path.write_text("a,b\n1,2\n")
    assert looks_like_microdata(path) is not None


def test_new_format_stata_magic_string_is_caught_even_when_renamed(tmp_path):
    path = tmp_path / "results.csv"
    path.write_bytes(b"<stata_dta>" + b"\x00" * 20)
    assert looks_like_microdata(path) is not None


def test_old_format_stata_header_is_caught_even_when_renamed(tmp_path):
    """The exact 4-byte pattern real QLFS/NHTS .dta files on this machine carry: release=113
    (Stata 8/9), byteorder=2, filetype=1, unused=0 -- confirmed directly against
    qlfs-2025-q2-v1.dta and nhts-2020-person.dta during this test's own construction, not
    invented."""
    path = tmp_path / "renamed_extract.csv"
    path.write_bytes(bytes([113, 2, 1, 0]) + b"\x00" * 20)
    reason = looks_like_microdata(path)
    assert reason is not None
    assert "old-format" in reason


def test_old_format_detector_does_not_fire_on_an_arbitrary_binary_file(tmp_path):
    """The false-positive guard this detector needs: a file that merely starts with a byte in
    the valid release-number range must NOT be flagged unless the byteorder, filetype and
    unused fields also match -- otherwise ordinary binary files (PNGs, pickles, whatever)
    would trip this constantly."""
    path = tmp_path / "figure.png"
    path.write_bytes(bytes([113, 99, 250, 7]) + b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    assert looks_like_microdata(path) is None


def test_a_genuine_results_csv_is_not_flagged(tmp_path):
    path = tmp_path / "calibration_fit.csv"
    path.write_text("moment,simulated_mean\ndiscouraged_share,0.13\n")
    assert looks_like_microdata(path) is None
