import hashlib
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import chromadb
import pytest

from rotation_tracker.serving.chroma import Chroma

A, B = "AAAAAAAAAAA", "BBBBBBBBBBB"


def write_store(path: Path) -> None:
    """A synthetic store in transcript·lab's shape, written by the pinned chromadb client."""
    client = chromadb.PersistentClient(path=str(path))
    raw = client.create_collection("raw_transcripts", embedding_function=None)
    raw_vectors: list[Sequence[float]] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    raw.add(
        ids=[f"raw_transcript:{A}", f"raw_transcript:{B}"],
        embeddings=raw_vectors,
        documents=["{}", "{}"],
    )
    chunks = client.create_collection("transcript_chunks", embedding_function=None)
    rows = [(A, 1, 30.0, 60.5), (A, 0, 0.0, 30.0), (B, 0, 0.0, 12.0)]
    vectors: list[Sequence[float]] = [[float(i), 1.0, 0.0] for _, i, _, _ in rows]
    chunks.add(
        ids=[f"{v}:{i}" for v, i, _, _ in rows],
        embeddings=vectors,
        documents=[f"Synthetic chunk {i} of {v}." for v, i, _, _ in rows],
        metadatas=[
            {"video_id": v, "chunk_index": i, "start_seconds": s, "end_seconds": e}
            for v, i, s, e in rows
        ],
    )


def test_reads_what_chromadb_wrote_without_touching_the_file(tmp_path: Path) -> None:
    write_store(tmp_path)
    file = tmp_path / "chroma.sqlite3"
    before = hashlib.sha256(file.read_bytes()).hexdigest()

    store = Chroma(tmp_path)
    assert store.count("raw_transcripts") == 2
    assert store.count("raw_transcripts", [f"raw_transcript:{A}", "raw_transcript:none"]) == 1
    assert store.count("transcript_chunks") == 3
    assert store.count_where("transcript_chunks", "video_id", [A]) == 2
    assert store.count_where("transcript_chunks", "video_id", [A, B]) == 3
    assert store.chunks(A) == [
        {"idx": 0, "start_s": 0.0, "end_s": 30.0, "text": f"Synthetic chunk 0 of {A}."},
        {"idx": 1, "start_s": 30.0, "end_s": 60.5, "text": f"Synthetic chunk 1 of {A}."},
    ]
    assert store.chunks("CCCCCCCCCCC") == []

    assert hashlib.sha256(file.read_bytes()).hexdigest() == before


def test_a_missing_store_or_collection_is_an_ordinary_error(tmp_path: Path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        Chroma(tmp_path / "nowhere").count("raw_transcripts")
    assert not (tmp_path / "nowhere").exists()

    write_store(tmp_path)
    with pytest.raises(LookupError):
        Chroma(tmp_path).count("no_such_collection")
