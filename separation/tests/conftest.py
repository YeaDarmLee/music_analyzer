import pytest


@pytest.fixture(autouse=True)
def keep_intermediates_for_legacy_tests(monkeypatch):
    """Pipeline tests read job outputs after an analysis; lifecycle tests switch this off explicitly."""
    monkeypatch.setenv("MUSIC_KEEP_INTERMEDIATES", "1")
    monkeypatch.setenv("MUSIC_KEEP_BENCHMARK_AUDIO", "1")
