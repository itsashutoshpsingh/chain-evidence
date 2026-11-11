from chain_evidence import providers


def test_unset_key_skips_provider(tmp_path, monkeypatch):
    f = tmp_path / "p.toml"
    f.write_text('[[provider]]\nname="k"\nchain="ethereum"\nurl="https://h/v2/${KEY_X}"\n'
                 '[[provider]]\nname="free"\nchain="ethereum"\nurl="https://free"\n')
    monkeypatch.delenv("KEY_X", raising=False)
    assert [p.name for p in providers.load(path=f)] == ["free"]
    monkeypatch.setenv("KEY_X", "secret123")
    ps = providers.load(path=f)
    assert ps[0].url.endswith("secret123")


def test_example_config_loads():
    assert {p.chain for p in providers.load(path=providers.ROOT / "providers.example.toml")} == {"ethereum", "base"}
