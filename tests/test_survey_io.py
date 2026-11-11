import csv

from chain_evidence import survey


def test_append_survives_schema_change(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "RESULTS", tmp_path)
    survey._append("x.csv", [{"a": 1, "b": 2}])
    survey._append("x.csv", [{"a": 3, "b": 4}])
    survey._append("x.csv", [{"a": 5, "c": 6, "b": 7}])
    rows = list(csv.DictReader(open(tmp_path / "x.csv")))
    assert [r["a"] for r in rows] == ["1", "3", "5"]
    assert rows[2]["c"] == "6" and rows[0]["c"] == "" and rows[2]["b"] == "7"
