"""Tests for `pypi_winnow_downloads/__init__.py` — primarily the
`PackageNotFoundError` defensive fallback for `__version__`.
"""

import importlib
import importlib.metadata

import pytest

import pypi_winnow_downloads


def test_init_falls_back_to_dev_version_when_package_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`__init__.py:7-8` declares a defensive fallback: if `importlib.metadata`
    can't find an installed `pypi-winnow-downloads` package (i.e., we're
    running from source without an editable install, or the dist-info is
    missing), `__version__` is set to `"0.0.0+dev"` instead of crashing.

    Patch `importlib.metadata.version` to raise `PackageNotFoundError`,
    `importlib.reload` the package, and assert the fallback fires. After
    the test, reload again with the patch undone so subsequent tests see
    the real installed version on `pypi_winnow_downloads.__version__`.
    """
    real_version = importlib.metadata.version

    def raising_version(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", raising_version)

    try:
        importlib.reload(pypi_winnow_downloads)
        assert pypi_winnow_downloads.__version__ == "0.0.0+dev"
    finally:
        # Restore the real version() and reload so other tests aren't poisoned
        # with the dev-version fallback string.
        monkeypatch.setattr(importlib.metadata, "version", real_version)
        importlib.reload(pypi_winnow_downloads)
