"""transcript·lab's Chroma store as the viewer reads it: from ``chroma.sqlite3``, read-only.

The viewer needs ids, documents and metadata, never vectors. chromadb's own client loads a
collection's HNSW index on its first read and replays any of the write log the index has not
applied; when that index is behind or damaged, the native code kills the whole process
(SIGBUS/SIGSEGV) and Python cannot catch it. The SQLite file holds every document and metadata
value, kept current with the log, so opening it with ``mode=ro`` needs no index, cannot write, and
fails as an ordinary exception. The schema is chromadb 1.5.9's, the version pyproject pins to
transcript·lab's own.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

SEGMENT_SQL = """
SELECT s.id FROM segments s JOIN collections c ON c.id = s.collection
WHERE c.name = ? AND s.scope = 'METADATA'"""

CHUNKS_SQL = """
SELECT max(CASE WHEN m.key = 'chunk_index' THEN m.int_value END),
       max(CASE WHEN m.key = 'start_seconds' THEN coalesce(m.float_value, m.int_value) END),
       max(CASE WHEN m.key = 'end_seconds' THEN coalesce(m.float_value, m.int_value) END),
       max(CASE WHEN m.key = 'chroma:document' THEN m.string_value END)
FROM embeddings e JOIN embedding_metadata m ON m.id = e.id
WHERE e.segment_id = ?
  AND e.id IN (SELECT id FROM embedding_metadata WHERE key = 'video_id' AND string_value = ?)
GROUP BY e.id"""


class Chroma:
    def __init__(self, path: Path) -> None:
        self.file = path / "chroma.sqlite3"

    @contextmanager
    def _con(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(f"{self.file.as_uri()}?mode=ro", uri=True)) as con:
            yield con

    @staticmethod
    def _segment(con: sqlite3.Connection, collection: str) -> str:
        row = con.execute(SEGMENT_SQL, (collection,)).fetchone()
        if row is None:
            raise LookupError(f"no Chroma collection {collection!r}")
        return str(row[0])

    def count(self, collection: str, ids: list[str] | None = None) -> int:
        """Records in a collection, or how many of ``ids`` it holds."""
        with self._con() as con:
            seg = self._segment(con, collection)
            args: tuple[str, ...]
            if ids is None:
                sql, args = "SELECT count(*) FROM embeddings WHERE segment_id = ?", (seg,)
            else:
                sql = """SELECT count(*) FROM embeddings WHERE segment_id = ?
                         AND embedding_id IN (SELECT value FROM json_each(?))"""
                args = (seg, json.dumps(ids))
            return int(con.execute(sql, args).fetchone()[0])

    def count_where(self, collection: str, key: str, values: list[str]) -> int:
        """Records whose string metadata ``key`` is one of ``values``."""
        with self._con() as con:
            seg = self._segment(con, collection)
            row = con.execute(
                """SELECT count(*) FROM embeddings e JOIN embedding_metadata m ON m.id = e.id
                   WHERE e.segment_id = ? AND m.key = ?
                     AND m.string_value IN (SELECT value FROM json_each(?))""",
                (seg, key, json.dumps(values)),
            ).fetchone()
            return int(row[0])

    def chunks(self, video_id: str) -> list[dict[str, Any]]:
        """One video's ``transcript_chunks``, in order."""
        with self._con() as con:
            seg = self._segment(con, "transcript_chunks")
            rows = con.execute(CHUNKS_SQL, (seg, video_id)).fetchall()
        out = [{"idx": i, "start_s": s, "end_s": e, "text": d} for i, s, e, d in rows]
        return sorted(out, key=lambda c: c["idx"] or 0)
