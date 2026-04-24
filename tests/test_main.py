# SPDX-License-Identifier: Apache-2.0
import pytest

from pypi_winnow_downloads.__main__ import main


def test_main_exits_with_not_implemented_message() -> None:
    with pytest.raises(SystemExit, match="not implemented"):
        main()
