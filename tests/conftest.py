import pytest

@pytest.fixture(autouse=True)
def isolated_molid_env(tmp_path, monkeypatch):
    """
    Ensure all MolID config writes during tests go into a temporary file,
    not ~/.molid.env. This prevents pytest from polluting your real config.
    """
    monkeypatch.setenv("MOLID_ENV_FILE", str(tmp_path / "molid_test.env"))
