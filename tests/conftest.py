import gzip
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


def load(name):
    with gzip.open(FIX / name, "rt") as f:
        return json.load(f)


@pytest.fixture(params=sorted(p.name for p in FIX.glob("*_block_*.json.gz")))
def block_fixture(request):
    return load(request.param)
