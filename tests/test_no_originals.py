#!/usr/bin/env python3
"""The no-originals guard.

This project reads two commercial games' level files and ships none of them.
That is a promise, and a promise a repository can break by accident -- a stray
copy under a scratch directory, a fixture someone found convenient, an
"example" pasted in during a debugging session.  So the promise is a test.

``tests/known-original-md5s.json`` holds the md5 of every level file the work
was measured against and nothing else: 11 campaign ``.kitty`` levels and the 24
level gifs of the compilation, 35 hashes.  A hash identifies a file without
carrying any of it, which is the only reason this list can live in a public
repository at all.

The test walks the whole tree and fails if any file hashes to any of them.  It
also runs as a script, so the guard can be pointed at a FRESH CLONE of the
published repository -- checking the tree that actually went out, not the one
that was meant to::

    python3 tests/test_no_originals.py /path/to/a/fresh/clone
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIST = os.path.join(HERE, "known-original-md5s.json")

#: directories a walk never needs to descend into.  ``.git`` is excluded because
#: its object store holds COMPRESSED blobs, which never match a plain md5 -- the
#: working tree is where an original would actually be readable.
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "build", "dist"}


def known_md5s(path: str = LIST) -> set:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    got = set(payload["md5"])
    if len(got) != payload["_count"]:
        raise AssertionError("the list claims %d hashes and holds %d"
                             % (payload["_count"], len(got)))
    return got


def scan(root: str, wanted: set):
    """Every file under ``root`` whose md5 is in ``wanted``."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                digest = hashlib.md5(fh.read()).hexdigest()
            if digest in wanted:
                hits.append((os.path.relpath(path, root), digest))
    return hits


# ------------------------------------------------------------------- the test
def test_the_list_is_the_measured_corpus():
    with open(LIST, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["_count"] == 35
    assert len(known_md5s()) == 35
    assert all(len(h) == 32 and all(c in "0123456789abcdef" for c in h)
               for h in payload["md5"])


def test_no_original_level_file_is_in_this_repository():
    hits = scan(ROOT, known_md5s())
    assert not hits, (
        "these files are original level data and must never be in this repository: %s"
        % ", ".join("%s (%s)" % (p, d) for p, d in hits))


def test_the_guard_would_notice(tmp_path):
    """A guard nobody has seen go red is not a guard.

    Planting a file whose md5 IS one of the listed ones is impossible without
    the original, so the discrimination is proven the other way round: the
    scanner is asked for a hash it can actually find, and must find it.
    """
    body = b"not an original, but we can ask the scanner to look for its hash\n"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "planted.bin").write_bytes(body)
    (tmp_path / "innocent.txt").write_bytes(b"nothing to see\n")

    digest = hashlib.md5(body).hexdigest()
    hits = scan(str(tmp_path), {digest})
    assert hits == [(os.path.join("sub", "planted.bin"), digest)]
    assert scan(str(tmp_path), {"0" * 32}) == []


def test_the_scanner_skips_the_git_object_store(tmp_path):
    body = b"pretend original\n"
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "blob").write_bytes(body)
    assert scan(str(tmp_path), {hashlib.md5(body).hexdigest()}) == []


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else ROOT
    found = scan(target, known_md5s())
    if found:
        print("FAILED -- original level data in %s:" % target)
        for path, digest in found:
            print("  %s  %s" % (digest, path))
        raise SystemExit(1)
    print("no-originals guard PASSED over %s" % os.path.abspath(target))
