"""Frozen raw files must never change silently (docs/data_sources.md)."""

import csv

import pytest

from src import config
from src.ingest import IngestError, Manifest, rel, sha256_file


@pytest.fixture
def raw_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    path = tmp_path / "data" / "raw" / "example.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"score": 17}')
    return path


def test_a_redownloaded_file_that_changed_upstream_fails(raw_file, tmp_path):
    manifest = Manifest(tmp_path / "manifest.csv")
    manifest.record(raw_file, source="test", dataset="example")
    raw_file.write_text('{"score": 18}')  # a fresh clone downloads a corrected upstream version
    with pytest.raises(IngestError, match="--refresh"):
        manifest.record(raw_file, source="test", dataset="example")


def test_an_identical_redownload_keeps_the_original_row(raw_file, tmp_path):
    path = tmp_path / "manifest.csv"
    Manifest(path).record(raw_file, source="test", dataset="example")
    before = path.read_text()
    content = raw_file.read_bytes()
    raw_file.unlink()  # a fresh clone has the manifest but not the file
    reloaded = Manifest(path)
    assert not reloaded.is_frozen(raw_file, refresh=False)  # so it is downloaded again
    raw_file.write_bytes(content)
    reloaded.record(raw_file, source="test", dataset="example")
    assert path.read_text() == before


def test_refresh_accepts_the_new_version(raw_file, tmp_path):
    path = tmp_path / "manifest.csv"
    Manifest(path).record(raw_file, source="test", dataset="example")
    raw_file.write_text('{"score": 18}')
    Manifest(path, refresh=True).record(raw_file, source="test", dataset="example")
    rows = {r["local_path"]: r for r in csv.DictReader(open(path))}
    assert rows[rel(raw_file)]["sha256"] == sha256_file(raw_file)


def test_a_present_file_that_changed_fails(raw_file, tmp_path):
    manifest = Manifest(tmp_path / "manifest.csv")
    manifest.record(raw_file, source="test", dataset="example")
    raw_file.write_text("tampered")
    with pytest.raises(IngestError):
        manifest.is_frozen(raw_file, refresh=False)
