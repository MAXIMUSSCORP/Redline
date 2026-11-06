import copy
from dataclasses import replace
from pathlib import Path

import pytest

from redline.config import Config, load_config
from redline.model import Confidence, Method, Source, Value

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def test_cfg() -> Config:
    return load_config(ROOT / "tests" / "test_config")


@pytest.fixture
def skeleton_cfg() -> Config:
    return load_config(ROOT / "config")


@pytest.fixture
def val():
    def make(value, confidence=Confidence.HIGH, locator="test", raw=None) -> Value:
        return Value(value, Source("test.csv", locator, Method.CSV, confidence), raw)

    return make


@pytest.fixture
def cfg_set():
    def make(cfg: Config, path: tuple[str, ...], value) -> Config:
        cec = copy.deepcopy(cfg.cec)
        node = cec
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        return replace(cfg, cec=cec)

    return make


@pytest.fixture
def cfg_unverify(cfg_set):
    def make(cfg: Config, table: str) -> Config:
        return cfg_set(cfg, ("tables", table, "verified"), False)

    return make
