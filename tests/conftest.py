import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kittygif.table import DIALECTS, IdTable, Palette  # noqa: E402


@pytest.fixture
def table():
    """The packaged RWIA table -- the default dialect, and what this suite always
    meant by "the table" before a second one existed."""
    return IdTable.load()


@pytest.fixture
def flash():
    """The Flash dialect's table."""
    return IdTable.load(dialect="flash")


@pytest.fixture(params=sorted(DIALECTS))
def any_table(request):
    """Every packaged dialect in turn, for the arms that are about SHAPE.

    An arm parametrised on this one holds for each dialect BY NAME: adding a
    dialect adds its runs automatically, and none of them can be skipped
    silently, which is the failure mode a lone ``if`` around a second table has.
    """
    return IdTable.load(dialect=request.param)


@pytest.fixture
def palette():
    return Palette.load()
