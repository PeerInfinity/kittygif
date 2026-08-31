import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kittygif.table import IdTable, Palette  # noqa: E402


@pytest.fixture
def table():
    return IdTable.load()


@pytest.fixture
def palette():
    return Palette.load()
