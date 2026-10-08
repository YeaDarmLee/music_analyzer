import pytest


@pytest.fixture(autouse=True)
def keep_intermediates_for_legacy_tests(monkeypatch):
    """Pipeline tests read job outputs after an analysis; lifecycle tests switch this off explicitly."""
    monkeypatch.setenv("MUSIC_KEEP_INTERMEDIATES", "1")
    monkeypatch.setenv("MUSIC_KEEP_BENCHMARK_AUDIO", "1")


@pytest.fixture(autouse=True, scope="session")
def service_data_untouched():
    """Automated tests run in tmp_path roots; they must never create analyses, jobs or inputs in the service data root."""
    from music_analyzer.common import project_root
    root = project_root() / "data/separation"
    snapshot = lambda: {sub: sorted(p.name for p in (root / sub).iterdir()) if (root / sub).is_dir() else [] for sub in ("web", "jobs", "inputs")}
    before = snapshot()
    yield
    assert snapshot() == before, "a test wrote into the service data root (data/separation/{web,jobs,inputs})"
