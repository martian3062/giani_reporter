from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .schemas import Episode, RenderJob, Story


DEMO_STORIES: tuple[dict[str, Any], ...] = (
    {
        "id": "demo-story-source-check",
        "title": "[DEMO] Replace this card with a verified AI source",
        "source": "Demo workspace",
        "url": "https://example.invalid/newsroom/demo-source-check",
        "published_at": "2000-01-01T00:00:00Z",
        "summary": (
            "This is rehearsal material. It contains no current news claim and "
            "must be replaced or kept clearly marked as demo content."
        ),
        "why_it_matters": (
            "It lets the production workflow be tested without fabricating a "
            "current event."
        ),
        "score": 0.0,
        "selected": True,
        "topic": "demo",
        "is_demo": True,
    },
    {
        "id": "demo-story-editorial-angle",
        "title": "[DEMO] Practice writing a human editorial angle",
        "source": "Demo workspace",
        "url": "https://example.invalid/newsroom/demo-editorial-angle",
        "published_at": "2000-01-01T00:00:00Z",
        "summary": (
            "This placeholder exists only to exercise story selection, "
            "drafting, review, and compliance controls."
        ),
        "why_it_matters": (
            "The angle remains a deliberate human input even when the draft is "
            "generated offline."
        ),
        "score": 0.0,
        "selected": True,
        "topic": "demo",
        "is_demo": True,
    },
    {
        "id": "demo-story-render-handoff",
        "title": "[DEMO] Rehearse the voice and render handoff",
        "source": "Demo workspace",
        "url": "https://example.invalid/newsroom/demo-render-handoff",
        "published_at": "2000-01-01T00:00:00Z",
        "summary": (
            "This placeholder creates visibly non-publishable artifacts for "
            "local voice and video pipeline testing."
        ),
        "why_it_matters": (
            "It verifies artifact paths and job progress before paid providers "
            "are configured."
        ),
        "score": 0.0,
        "selected": True,
        "topic": "demo",
        "is_demo": True,
    },
)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class Repository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS stories (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    why_it_matters TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0,
                    selected INTEGER NOT NULL DEFAULT 0,
                    topic TEXT NOT NULL DEFAULT 'general',
                    is_demo INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    date TEXT NOT NULL,
                    angle TEXT NOT NULL,
                    story_ids TEXT NOT NULL,
                    script TEXT NOT NULL DEFAULT '',
                    sections TEXT NOT NULL DEFAULT '{}',
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    hashtags TEXT NOT NULL DEFAULT '[]',
                    overlays TEXT NOT NULL DEFAULT '[]',
                    cues TEXT NOT NULL DEFAULT '[]',
                    word_count INTEGER NOT NULL DEFAULT 0,
                    runtime_seconds INTEGER NOT NULL DEFAULT 0,
                    compliance TEXT NOT NULL DEFAULT '{}',
                    voice_path TEXT NOT NULL DEFAULT '',
                    voice_provider TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 1,
                    voice_revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS render_jobs (
                    id TEXT PRIMARY KEY,
                    episode_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL,
                    output_path TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    episode_revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (episode_id) REFERENCES episodes(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    format TEXT NOT NULL,
                    status TEXT NOT NULL,
                    headline TEXT NOT NULL DEFAULT '',
                    caption TEXT NOT NULL DEFAULT '',
                    hashtags TEXT NOT NULL DEFAULT '[]',
                    alt_text TEXT NOT NULL DEFAULT '',
                    ai_disclosure TEXT NOT NULL DEFAULT '',
                    image_prompts TEXT NOT NULL DEFAULT '[]',
                    direction_provider TEXT NOT NULL DEFAULT '',
                    image_provider TEXT NOT NULL DEFAULT '',
                    checks TEXT NOT NULL DEFAULT '{}',
                    revision INTEGER NOT NULL DEFAULT 1,
                    approved_revision INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS post_assets (
                    id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'image',
                    provider TEXT NOT NULL DEFAULT '',
                    prompt_used TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL,
                    mime TEXT NOT NULL DEFAULT 'image/jpeg',
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    bytes INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL DEFAULT '',
                    public_token TEXT NOT NULL UNIQUE,
                    is_demo INTEGER NOT NULL DEFAULT 0,
                    post_revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS post_publications (
                    id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    post_revision INTEGER NOT NULL,
                    container_id TEXT NOT NULL DEFAULT '',
                    media_id TEXT NOT NULL DEFAULT '',
                    permalink TEXT NOT NULL DEFAULT '',
                    ig_user_id TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_stories_published
                    ON stories(published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_episodes_updated
                    ON episodes(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_render_jobs_episode
                    ON render_jobs(episode_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_posts_updated
                    ON posts(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_post_assets_post
                    ON post_assets(post_id, position ASC);
                CREATE INDEX IF NOT EXISTS idx_post_publications_post
                    ON post_publications(post_id, created_at DESC);

                /* One live publish attempt per revision. A failed attempt may
                   be retried; a pending or published one may never be
                   duplicated by a double click or a retried request. */
                CREATE UNIQUE INDEX IF NOT EXISTS idx_post_publication_once
                    ON post_publications(post_id, post_revision)
                    WHERE status != 'failed';
                """
            )
            episode_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(episodes)"
                ).fetchall()
            }
            voice_revision_added = "voice_revision" not in episode_columns
            if "revision" not in episode_columns:
                connection.execute(
                    "ALTER TABLE episodes "
                    "ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"
                )
            if voice_revision_added:
                connection.execute(
                    "ALTER TABLE episodes "
                    "ADD COLUMN voice_revision INTEGER NOT NULL DEFAULT 0"
                )
                connection.execute(
                    """
                    UPDATE episodes
                    SET voice_revision = revision
                    WHERE voice_path != ''
                    """
                )

            render_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(render_jobs)"
                ).fetchall()
            }
            if "episode_revision" not in render_columns:
                connection.execute(
                    "ALTER TABLE render_jobs "
                    "ADD COLUMN episode_revision INTEGER NOT NULL DEFAULT 0"
                )
                connection.execute(
                    """
                    UPDATE render_jobs
                    SET episode_revision = COALESCE(
                        (
                            SELECT episodes.revision
                            FROM episodes
                            WHERE episodes.id = render_jobs.episode_id
                        ),
                        0
                    )
                    """
                )

    def seed_demo_stories(self, timestamp: str) -> None:
        with self.connect() as connection:
            for story in DEMO_STORIES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO stories (
                        id, title, source, url, published_at, summary,
                        why_it_matters, score, selected, topic, is_demo,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        story["id"],
                        story["title"],
                        story["source"],
                        story["url"],
                        story["published_at"],
                        story["summary"],
                        story["why_it_matters"],
                        story["score"],
                        int(story["selected"]),
                        story["topic"],
                        int(story["is_demo"]),
                        timestamp,
                        timestamp,
                    ),
                )

    @staticmethod
    def _story_from_row(row: sqlite3.Row) -> Story:
        return Story(
            id=row["id"],
            title=row["title"],
            source=row["source"],
            url=row["url"],
            published_at=row["published_at"],
            summary=row["summary"],
            why_it_matters=row["why_it_matters"],
            score=float(row["score"]),
            selected=bool(row["selected"]),
            topic=row["topic"],
            is_demo=bool(row["is_demo"]),
        )

    @staticmethod
    def _episode_from_row(row: sqlite3.Row) -> Episode:
        return Episode(
            id=row["id"],
            kind=row["kind"],
            status=row["status"],
            date=row["date"],
            angle=row["angle"],
            story_ids=_json_load(row["story_ids"], []),
            script=row["script"],
            sections=_json_load(row["sections"], {}),
            title=row["title"],
            description=row["description"],
            hashtags=_json_load(row["hashtags"], []),
            overlays=_json_load(row["overlays"], []),
            cues=_json_load(row["cues"], []),
            word_count=int(row["word_count"]),
            runtime_seconds=int(row["runtime_seconds"]),
            compliance=_json_load(row["compliance"], {}),
            revision=int(row["revision"]),
            voice_revision=int(row["voice_revision"]),
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _render_job_from_row(row: sqlite3.Row) -> RenderJob:
        return RenderJob(
            id=row["id"],
            episode_id=row["episode_id"],
            status=row["status"],
            progress=int(row["progress"]),
            stage=row["stage"],
            output_path=row["output_path"],
            error=row["error"],
            episode_revision=int(row["episode_revision"]),
        )

    def list_stories(
        self,
        *,
        selected: bool | None = None,
        topic: str | None = None,
        limit: int = 100,
    ) -> list[Story]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if selected is not None:
            clauses.append("selected = ?")
            parameters.append(int(selected))
        if topic:
            clauses.append("topic = ?")
            parameters.append(topic)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM stories
                {where}
                ORDER BY selected DESC, is_demo ASC, published_at DESC, score DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._story_from_row(row) for row in rows]

    def get_story(self, story_id: str) -> Story | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM stories WHERE id = ?", (story_id,)
            ).fetchone()
        return self._story_from_row(row) if row else None

    def get_stories_by_ids(self, story_ids: Iterable[str]) -> list[Story]:
        ids = list(story_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM stories WHERE id IN ({placeholders})", ids
            ).fetchall()
        by_id = {row["id"]: self._story_from_row(row) for row in rows}
        return [by_id[story_id] for story_id in ids if story_id in by_id]

    def select_story(
        self, story_id: str, selected: bool, timestamp: str
    ) -> Story | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE stories
                SET selected = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(selected), timestamp, story_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_story(story_id)

    def upsert_stories(
        self, stories: Iterable[dict[str, Any]], timestamp: str
    ) -> int:
        count = 0
        with self.connect() as connection:
            for story in stories:
                connection.execute(
                    """
                    INSERT INTO stories (
                        id, title, source, url, published_at, summary,
                        why_it_matters, score, selected, topic, is_demo,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        source = excluded.source,
                        url = excluded.url,
                        published_at = excluded.published_at,
                        summary = excluded.summary,
                        why_it_matters = excluded.why_it_matters,
                        score = excluded.score,
                        topic = excluded.topic,
                        is_demo = excluded.is_demo,
                        updated_at = excluded.updated_at
                    """,
                    (
                        story["id"],
                        story["title"],
                        story["source"],
                        story["url"],
                        story["published_at"],
                        story["summary"],
                        story["why_it_matters"],
                        float(story.get("score", 0)),
                        int(story.get("selected", False)),
                        story.get("topic", "general"),
                        int(story.get("is_demo", False)),
                        timestamp,
                        timestamp,
                    ),
                )
                count += 1
        return count

    def create_episode(self, values: dict[str, Any]) -> Episode:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO episodes (
                    id, kind, status, date, angle, story_ids, script,
                    sections, title, description, hashtags, overlays, cues,
                    word_count, runtime_seconds, compliance, voice_path,
                    voice_provider, revision, voice_revision, created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"],
                    values["kind"],
                    values["status"],
                    values["date"],
                    values["angle"],
                    json.dumps(values["story_ids"]),
                    values.get("script", ""),
                    json.dumps(values.get("sections", {})),
                    values.get("title", ""),
                    values.get("description", ""),
                    json.dumps(values.get("hashtags", [])),
                    json.dumps(values.get("overlays", [])),
                    json.dumps(values.get("cues", [])),
                    int(values.get("word_count", 0)),
                    int(values.get("runtime_seconds", 0)),
                    json.dumps(values.get("compliance", {})),
                    values.get("voice_path", ""),
                    values.get("voice_provider", ""),
                    int(values.get("revision", 1)),
                    int(values.get("voice_revision", 0)),
                    values["created_at"],
                    values["updated_at"],
                ),
            )
        episode = self.get_episode(values["id"])
        assert episode is not None
        return episode

    def get_episode(self, episode_id: str) -> Episode | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
        return self._episode_from_row(row) if row else None

    def list_episodes(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Episode]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            parameters.append(kind)
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM episodes
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._episode_from_row(row) for row in rows]

    def update_episode(
        self, episode_id: str, values: dict[str, Any], timestamp: str
    ) -> Episode | None:
        if not values:
            return self.get_episode(episode_id)
        json_fields = {
            "story_ids",
            "sections",
            "hashtags",
            "overlays",
            "cues",
            "compliance",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            parameters.append(json.dumps(value) if key in json_fields else value)
        assignments.append("updated_at = ?")
        parameters.extend([timestamp, episode_id])
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE episodes
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_episode(episode_id)

    def get_episode_internal(self, episode_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_episode_content(
        self,
        episode_id: str,
        values: dict[str, Any],
        timestamp: str,
        *,
        expected_revision: int | None = None,
    ) -> Episode | None:
        """Commit an editorial revision and invalidate derived artifacts atomically."""
        if not values:
            return self.get_episode(episode_id)
        json_fields = {
            "story_ids",
            "sections",
            "hashtags",
            "overlays",
            "cues",
            "compliance",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            parameters.append(json.dumps(value) if key in json_fields else value)
        assignments.extend(
            [
                "revision = revision + 1",
                "voice_path = ''",
                "voice_provider = ''",
                "voice_revision = 0",
                "updated_at = ?",
            ]
        )
        parameters.extend([timestamp, episode_id])
        revision_clause = ""
        if expected_revision is not None:
            revision_clause = " AND revision = ?"
            parameters.append(expected_revision)
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE episodes
                SET {", ".join(assignments)}
                WHERE id = ?{revision_clause}
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                """
                UPDATE render_jobs
                SET status = 'failed',
                    stage = 'invalidated',
                    error = 'Invalidated by a newer editorial revision',
                    updated_at = ?
                WHERE episode_id = ?
                  AND stage != 'invalidated'
                """,
                (timestamp, episode_id),
            )
        return self.get_episode(episode_id)

    def update_episode_if_revision(
        self,
        episode_id: str,
        values: dict[str, Any],
        timestamp: str,
        *,
        expected_revision: int,
    ) -> Episode | None:
        if not values:
            internal = self.get_episode_internal(episode_id)
            if (
                internal is None
                or int(internal["revision"]) != expected_revision
            ):
                return None
            return self.get_episode(episode_id)
        json_fields = {
            "story_ids",
            "sections",
            "hashtags",
            "overlays",
            "cues",
            "compliance",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            parameters.append(json.dumps(value) if key in json_fields else value)
        assignments.append("updated_at = ?")
        parameters.extend([timestamp, episode_id, expected_revision])
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE episodes
                SET {", ".join(assignments)}
                WHERE id = ? AND revision = ?
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_episode(episode_id)

    def update_episode_state_if_current(
        self,
        episode_id: str,
        *,
        values: dict[str, Any],
        expected_revision: int,
        expected_compliance: dict[str, bool],
        timestamp: str,
    ) -> Episode | None:
        """Update status/compliance without losing a concurrent gate change."""
        if not values:
            return self.get_episode(episode_id)
        json_fields = {"compliance"}
        assignments: list[str] = []
        parameters: list[Any] = []
        for key, value in values.items():
            if key not in {"status", "compliance"}:
                raise ValueError(f"unsupported episode state field: {key}")
            assignments.append(f"{key} = ?")
            parameters.append(
                json.dumps(value) if key in json_fields else value
            )
        assignments.append("updated_at = ?")
        parameters.extend(
            [
                timestamp,
                episode_id,
                expected_revision,
                json.dumps(expected_compliance),
            ]
        )
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE episodes
                SET {", ".join(assignments)}
                WHERE id = ?
                  AND revision = ?
                  AND compliance = ?
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_episode(episode_id)

    def commit_voice_if_current(
        self,
        episode_id: str,
        *,
        expected_revision: int,
        expected_previous_voice_path: str,
        voice_path: str,
        voice_provider: str,
        timestamp: str,
    ) -> Episode | None:
        """Attach voice only while it still matches the approved script revision."""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE episodes
                SET voice_path = ?,
                    voice_provider = ?,
                    voice_revision = revision,
                    updated_at = ?
                WHERE id = ?
                  AND revision = ?
                  AND status = 'approved'
                  AND voice_path = ?
                """,
                (
                    voice_path,
                    voice_provider,
                    timestamp,
                    episode_id,
                    expected_revision,
                    expected_previous_voice_path,
                ),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                """
                UPDATE render_jobs
                SET status = 'failed',
                    stage = 'invalidated',
                    error = 'Invalidated by a newer voice artifact',
                    updated_at = ?
                WHERE episode_id = ?
                  AND stage != 'invalidated'
                """,
                (timestamp, episode_id),
            )
        return self.get_episode(episode_id)

    def mark_episode_packaged_if_current(
        self,
        episode_id: str,
        *,
        expected_revision: int,
        render_job_id: str,
        expected_compliance: dict[str, bool],
        timestamp: str,
    ) -> Episode | None:
        """Linearize packaging against edits, voice changes, and render state."""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE episodes
                SET status = 'packaged', updated_at = ?
                WHERE id = ?
                  AND revision = ?
                  AND voice_revision = revision
                  AND status = 'approved'
                  AND compliance = ?
                  AND EXISTS (
                      SELECT 1
                      FROM render_jobs
                      WHERE render_jobs.id = ?
                        AND render_jobs.episode_id = episodes.id
                        AND render_jobs.episode_revision =
                            episodes.revision
                        AND render_jobs.status = 'complete'
                        AND render_jobs.progress = 100
                        AND render_jobs.output_path != ''
                  )
                """,
                (
                    timestamp,
                    episode_id,
                    expected_revision,
                    json.dumps(expected_compliance),
                    render_job_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_episode(episode_id)

    def create_render_job(
        self,
        values: dict[str, Any],
        *,
        expected_voice_path: str | None = None,
    ) -> RenderJob | None:
        with self.connect() as connection:
            episode = connection.execute(
                """
                SELECT revision, voice_revision, voice_path, status
                FROM episodes
                WHERE id = ?
                """,
                (values["episode_id"],),
            ).fetchone()
            expected_revision = int(values["episode_revision"])
            if (
                episode is None
                or episode["status"] != "approved"
                or int(episode["revision"]) != expected_revision
                or int(episode["voice_revision"]) != expected_revision
                or not str(episode["voice_path"]).strip()
                or (
                    expected_voice_path is not None
                    and episode["voice_path"] != expected_voice_path
                )
            ):
                return None
            connection.execute(
                """
                INSERT INTO render_jobs (
                    id, episode_id, status, progress, stage, output_path,
                    error, episode_revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"],
                    values["episode_id"],
                    values["status"],
                    values["progress"],
                    values["stage"],
                    values.get("output_path", ""),
                    values.get("error", ""),
                    expected_revision,
                    values["created_at"],
                    values["updated_at"],
                ),
            )
        job = self.get_render_job(values["id"])
        assert job is not None
        return job

    def get_render_job_internal(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM render_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def claim_render_job(
        self, job_id: str, timestamp: str
    ) -> RenderJob | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE render_jobs
                SET status = 'running',
                    progress = 15,
                    stage = 'loading_episode',
                    updated_at = ?
                WHERE id = ?
                  AND status = 'queued'
                  AND EXISTS (
                      SELECT 1
                      FROM episodes
                      WHERE episodes.id = render_jobs.episode_id
                        AND episodes.revision =
                            render_jobs.episode_revision
                        AND episodes.voice_revision =
                            render_jobs.episode_revision
                        AND episodes.voice_path != ''
                  )
                """,
                (timestamp, job_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_render_job(job_id)

    def update_render_job_if_current(
        self, job_id: str, values: dict[str, Any], timestamp: str
    ) -> RenderJob | None:
        assignments = [f"{key} = ?" for key in values]
        parameters = [*values.values(), timestamp, job_id]
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE render_jobs
                SET {", ".join(assignments)}, updated_at = ?
                WHERE id = ?
                  AND status = 'running'
                  AND EXISTS (
                      SELECT 1
                      FROM episodes
                      WHERE episodes.id = render_jobs.episode_id
                        AND episodes.revision =
                            render_jobs.episode_revision
                        AND episodes.voice_revision =
                            render_jobs.episode_revision
                        AND episodes.voice_path != ''
                  )
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_render_job(job_id)

    def fail_render_job_if_active(
        self, job_id: str, error: str, timestamp: str
    ) -> RenderJob | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE render_jobs
                SET status = 'failed',
                    stage = 'failed',
                    error = ?,
                    updated_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (error, timestamp, job_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_render_job(job_id)

    def update_render_job(
        self, job_id: str, values: dict[str, Any], timestamp: str
    ) -> RenderJob | None:
        assignments = [f"{key} = ?" for key in values]
        parameters = [*values.values(), timestamp, job_id]
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE render_jobs
                SET {", ".join(assignments)}, updated_at = ?
                WHERE id = ?
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_render_job(job_id)

    def get_render_job(self, job_id: str) -> RenderJob | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM render_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._render_job_from_row(row) if row else None

    def list_render_jobs(
        self,
        *,
        episode_id: str | None = None,
        limit: int = 100,
    ) -> list[RenderJob]:
        where = "WHERE episode_id = ?" if episode_id else ""
        parameters: list[Any] = [episode_id] if episode_id else []
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM render_jobs
                {where}
                ORDER BY updated_at DESC, rowid DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._render_job_from_row(row) for row in rows]

    def recover_interrupted_render_jobs(self, timestamp: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE render_jobs
                SET status = 'failed',
                    stage = 'interrupted',
                    error = 'Render worker restarted before completion',
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (timestamp,),
            )

    def invalidate_render_jobs(self, episode_id: str, timestamp: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE render_jobs
                SET status = 'failed',
                    stage = 'invalidated',
                    error = 'Invalidated by a newer editorial or voice revision',
                    updated_at = ?
                WHERE episode_id = ?
                  AND stage != 'invalidated'
                """,
                (timestamp, episode_id),
            )

    def latest_render_job(self, episode_id: str) -> RenderJob | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM render_jobs
                WHERE episode_id = ?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                (episode_id,),
            ).fetchone()
        return self._render_job_from_row(row) if row else None

    # -- Post Studio -------------------------------------------------------

    _POST_JSON_FIELDS = frozenset({"hashtags", "image_prompts", "checks"})

    @classmethod
    def _post_from_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["hashtags"] = _json_load(record.get("hashtags"), [])
        record["image_prompts"] = _json_load(record.get("image_prompts"), [])
        record["checks"] = _json_load(record.get("checks"), {})
        return record

    @staticmethod
    def _asset_from_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["is_demo"] = bool(record.get("is_demo"))
        return record

    def create_post(self, values: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO posts (
                    id, prompt, format, status, headline, caption, hashtags,
                    alt_text, ai_disclosure, image_prompts,
                    direction_provider, image_provider, checks, revision,
                    approved_revision, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"],
                    values["prompt"],
                    values["format"],
                    values["status"],
                    values.get("headline", ""),
                    values.get("caption", ""),
                    json.dumps(values.get("hashtags", [])),
                    values.get("alt_text", ""),
                    values.get("ai_disclosure", ""),
                    json.dumps(values.get("image_prompts", [])),
                    values.get("direction_provider", ""),
                    values.get("image_provider", ""),
                    json.dumps(values.get("checks", {})),
                    int(values.get("revision", 1)),
                    int(values.get("approved_revision", 0)),
                    values.get("error", ""),
                    values["created_at"],
                    values["updated_at"],
                ),
            )
        post = self.get_post(values["id"])
        assert post is not None
        return post

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM posts WHERE id = ?", (post_id,)
            ).fetchone()
        return self._post_from_row(row) if row else None

    def list_posts(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        where = "WHERE status = ?" if status else ""
        parameters: list[Any] = [status] if status else []
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM posts
                {where}
                ORDER BY updated_at DESC, rowid DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._post_from_row(row) for row in rows]

    def update_post(
        self,
        post_id: str,
        values: dict[str, Any],
        timestamp: str,
        *,
        expected_revision: int | None = None,
        bump_revision: bool = False,
        carry_assets: bool = False,
    ) -> dict[str, Any] | None:
        """Update a post, optionally opening a new revision.

        ``carry_assets`` keeps already generated slides attached across an edit
        that does not change the imagery, such as a caption fix. Without it the
        slides fall behind the revision and the ``assets_current`` gate closes.
        """
        assignments: list[str] = []
        parameters: list[Any] = []
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            parameters.append(
                json.dumps(value) if key in self._POST_JSON_FIELDS else value
            )
        if bump_revision:
            assignments.append("revision = revision + 1")
        assignments.append("updated_at = ?")
        parameters.append(timestamp)
        parameters.append(post_id)
        revision_clause = ""
        if expected_revision is not None:
            revision_clause = " AND revision = ?"
            parameters.append(expected_revision)
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE posts
                SET {", ".join(assignments)}
                WHERE id = ?{revision_clause}
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
            if bump_revision and carry_assets:
                connection.execute(
                    """
                    UPDATE post_assets
                    SET post_revision = (
                        SELECT revision FROM posts WHERE posts.id = ?
                    )
                    WHERE post_id = ?
                    """,
                    (post_id, post_id),
                )
        return self.get_post(post_id)

    def replace_post_assets(
        self,
        post_id: str,
        assets: Iterable[dict[str, Any]],
        *,
        expected_revision: int,
    ) -> list[dict[str, Any]] | None:
        """Swap in a fresh slide set, but only while the revision still matches."""
        rows = list(assets)
        with self.connect() as connection:
            current = connection.execute(
                "SELECT revision FROM posts WHERE id = ?", (post_id,)
            ).fetchone()
            if current is None or int(current["revision"]) != expected_revision:
                return None
            connection.execute(
                "DELETE FROM post_assets WHERE post_id = ?", (post_id,)
            )
            for asset in rows:
                connection.execute(
                    """
                    INSERT INTO post_assets (
                        id, post_id, position, kind, provider, prompt_used,
                        path, mime, width, height, bytes, sha256,
                        public_token, is_demo, post_revision, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset["id"],
                        post_id,
                        int(asset["position"]),
                        asset.get("kind", "image"),
                        asset.get("provider", ""),
                        asset.get("prompt_used", ""),
                        asset["path"],
                        asset.get("mime", "image/jpeg"),
                        int(asset.get("width", 0)),
                        int(asset.get("height", 0)),
                        int(asset.get("bytes", 0)),
                        asset.get("sha256", ""),
                        asset["public_token"],
                        int(bool(asset.get("is_demo", False))),
                        expected_revision,
                        asset["created_at"],
                    ),
                )
        return self.list_post_assets(post_id)

    def list_post_assets(self, post_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM post_assets
                WHERE post_id = ?
                ORDER BY position ASC
                """,
                (post_id,),
            ).fetchall()
        return [self._asset_from_row(row) for row in rows]

    def get_post_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM post_assets WHERE id = ?", (asset_id,)
            ).fetchone()
        return self._asset_from_row(row) if row else None

    def get_post_asset_by_token(self, token: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM post_assets WHERE public_token = ?", (token,)
            ).fetchone()
        return self._asset_from_row(row) if row else None

    def approve_post_if_current(
        self,
        post_id: str,
        *,
        expected_revision: int,
        checks: dict[str, bool],
        timestamp: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE posts
                SET status = 'approved',
                    approved_revision = revision,
                    checks = ?,
                    error = '',
                    updated_at = ?
                WHERE id = ?
                  AND revision = ?
                  AND status IN ('review', 'approved')
                """,
                (json.dumps(checks), timestamp, post_id, expected_revision),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_post(post_id)

    def create_publication(
        self, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Reserve the single publish slot for this revision, or refuse."""
        with self.connect() as connection:
            post = connection.execute(
                """
                SELECT revision, approved_revision, status
                FROM posts WHERE id = ?
                """,
                (values["post_id"],),
            ).fetchone()
            expected = int(values["post_revision"])
            if (
                post is None
                or post["status"] != "approved"
                or int(post["revision"]) != expected
                or int(post["approved_revision"]) != expected
            ):
                return None
            try:
                connection.execute(
                    """
                    INSERT INTO post_publications (
                        id, post_id, status, post_revision, container_id,
                        media_id, permalink, ig_user_id, error,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values["id"],
                        values["post_id"],
                        values.get("status", "pending"),
                        expected,
                        values.get("container_id", ""),
                        values.get("media_id", ""),
                        values.get("permalink", ""),
                        values.get("ig_user_id", ""),
                        values.get("error", ""),
                        values["created_at"],
                        values["updated_at"],
                    ),
                )
            except sqlite3.IntegrityError:
                return None
            connection.execute(
                """
                UPDATE posts
                SET status = 'publishing', updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (values["updated_at"], values["post_id"], expected),
            )
        return self.get_publication(values["id"])

    def get_publication(self, publication_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM post_publications WHERE id = ?",
                (publication_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_publication(
        self, publication_id: str, values: dict[str, Any], timestamp: str
    ) -> dict[str, Any] | None:
        assignments = [f"{key} = ?" for key in values]
        parameters = [*values.values(), timestamp, publication_id]
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE post_publications
                SET {", ".join(assignments)}, updated_at = ?
                WHERE id = ?
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_publication(publication_id)

    def finish_publication(
        self,
        publication_id: str,
        *,
        post_id: str,
        media_id: str,
        permalink: str,
        timestamp: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE post_publications
                SET status = 'published',
                    media_id = ?,
                    permalink = ?,
                    error = '',
                    updated_at = ?
                WHERE id = ? AND status != 'published'
                """,
                (media_id, permalink, timestamp, publication_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                """
                UPDATE posts
                SET status = 'published', updated_at = ?
                WHERE id = ?
                """,
                (timestamp, post_id),
            )
        return self.get_publication(publication_id)

    def fail_publication(
        self,
        publication_id: str,
        *,
        post_id: str,
        error: str,
        timestamp: str,
    ) -> dict[str, Any] | None:
        """Release the publish slot after a failure that produced no media."""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE post_publications
                SET status = 'failed', error = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ('published', 'failed')
                """,
                (error[:1000], timestamp, publication_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                """
                UPDATE posts
                SET status = 'approved', error = ?, updated_at = ?
                WHERE id = ? AND status = 'publishing'
                """,
                (error[:1000], timestamp, post_id),
            )
        return self.get_publication(publication_id)

    def list_publications(self, post_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM post_publications
                WHERE post_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (post_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_publications_since(self, timestamp: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM post_publications
                WHERE status IN ('published', 'creating', 'publishing', 'pending')
                  AND created_at >= ?
                """,
                (timestamp,),
            ).fetchone()
        return int(row["count"] or 0)

    def recover_interrupted_publications(self, timestamp: str) -> None:
        """A restart mid-publish must never silently retry a live post."""
        message = (
            "The API restarted during publishing. Check Instagram before "
            "retrying, in case the post went live."
        )
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE post_publications
                SET status = 'failed', error = ?, updated_at = ?
                WHERE status IN ('pending', 'creating', 'publishing')
                """,
                (message, timestamp),
            )
            connection.execute(
                """
                UPDATE posts
                SET status = 'approved', error = ?, updated_at = ?
                WHERE status = 'publishing'
                """,
                (message, timestamp),
            )

    def post_counts(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM posts GROUP BY status"
            ).fetchall()
            published = connection.execute(
                """
                SELECT COUNT(*) AS count FROM post_publications
                WHERE status = 'published'
                """
            ).fetchone()["count"]
        return {
            "posts_total": sum(int(row["count"]) for row in rows),
            "post_status_counts": {
                row["status"]: int(row["count"]) for row in rows
            },
            "posts_published": int(published or 0),
        }

    def overview_counts(self) -> dict[str, Any]:
        with self.connect() as connection:
            story_counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN selected = 1 THEN 1 ELSE 0 END) AS selected,
                    SUM(CASE WHEN is_demo = 1 THEN 1 ELSE 0 END) AS demo
                FROM stories
                """
            ).fetchone()
            episode_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM episodes GROUP BY status"
            ).fetchall()
            active_jobs = connection.execute(
                """
                SELECT COUNT(*) AS count FROM render_jobs
                WHERE status IN ('queued', 'running')
                """
            ).fetchone()["count"]
        return {
            "stories_total": int(story_counts["total"] or 0),
            "stories_selected": int(story_counts["selected"] or 0),
            "demo_stories": int(story_counts["demo"] or 0),
            "episodes_total": sum(int(row["count"]) for row in episode_rows),
            "episode_status_counts": {
                row["status"]: int(row["count"]) for row in episode_rows
            },
            "render_jobs_active": int(active_jobs or 0),
        }
