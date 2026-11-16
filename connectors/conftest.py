from collections.abc import Sequence

import pytest

_DESELECTED = pytest.StashKey[bool]()


def pytest_deselected(items: Sequence[pytest.Item]) -> None:
    if items:
        items[0].config.stash[_DESELECTED] = True


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    deselected = session.config.stash.get(_DESELECTED, False)
    if exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED and not deselected:
        session.exitstatus = pytest.ExitCode.OK
