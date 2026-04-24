# SPDX-License-Identifier: Apache-2.0
"""pypi-winnow-downloads — PyPI download badges filtered for non-CI traffic."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pypi-winnow-downloads")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"
