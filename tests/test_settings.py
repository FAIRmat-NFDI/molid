def test_molid_env_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLID_ENV_FILE", str(tmp_path / "molid_test.env"))
    # Reload settings to pick up the env var
    import importlib

    from molid.utils import settings

    importlib.reload(settings)
    assert str(tmp_path) in str(settings.ENV_FILE)
