import pytest

from sdd.infra.paths import event_store_file


def test_event_store_file_emits_deprecation_warning():
    with pytest.warns(DeprecationWarning, match="event_store_url"):
        event_store_file()
