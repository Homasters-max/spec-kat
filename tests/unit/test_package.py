import re
import importlib.metadata

import sdd


def test_package_importable() -> None:
    assert sdd is not None


def test_version_string_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", sdd.__version__) is not None


def test_entry_point_registered() -> None:
    eps = importlib.metadata.entry_points(group="console_scripts")
    names = {ep.name for ep in eps}
    assert "sdd" in names
