from tracker import state as state_mod


def test_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "seen.json")
    st = state_mod.load_state()
    assert st == {"listings": {}, "blocks": {}}


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "sub" / "seen.json")
    st = {"listings": {"Target::u": {"in_stock": True}}, "blocks": {}}
    state_mod.save_state(st)  # creates parent dir
    assert state_mod.load_state() == st
