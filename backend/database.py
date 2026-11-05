import os
import threading
from contextlib import contextmanager
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy.engine import URL

metadata = MetaData()

tasks = Table(
    "care_demo_tasks",
    metadata,
    Column("task_id", String(100), primary_key=True),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("category", String(32), nullable=False),
    Column("due_date", Date),
    Column("status", String(20), nullable=False),
    Column("assignee_id", String(100)),
    Column("requested_assignee_id", String(100)),
    Column("assignment_status", String(16), nullable=False),
    Column("source_id", String(100)),
    CheckConstraint(
        "category IN ('benefit', 'vaccination_checkup', 'regular_visit')",
        name="care_demo_category_check",
    ),
    CheckConstraint(
        "status IN ('확인 필요', '담당 요청', '진행 중', '완료', '해당 없음')",
        name="care_demo_status_check",
    ),
    CheckConstraint(
        "(assignment_status = 'unassigned' AND assignee_id IS NULL AND requested_assignee_id IS NULL) OR "
        "(assignment_status = 'pending' AND assignee_id IS NULL AND requested_assignee_id IS NOT NULL) OR "
        "(assignment_status = 'accepted' AND assignee_id IS NOT NULL AND requested_assignee_id IS NULL)",
        name="care_demo_assignment_check",
    ),
    CheckConstraint(
        "(assignment_status = 'pending' AND status = '담당 요청') OR "
        "(assignment_status <> 'pending' AND status <> '담당 요청')",
        name="care_demo_pending_status_check",
    ),
)

seed_markers = Table(
    "care_demo_seed_markers",
    metadata,
    Column("name", String(100), primary_key=True),
)

task_activity = Table(
    "care_demo_task_activity",
    metadata,
    Column("event_id", String(40), primary_key=True),
    Column("task_id", String(100), nullable=False, index=True),
    Column("kind", String(32), nullable=False),
    Column("detail", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ai_usage = Table(
    "care_demo_ai_usage",
    metadata,
    Column("request_id", String(40), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

SEED_MARKER = "chengdo_table_v1"
SEED_NOTICE = "[가상 CSV 시연] 기존 담당 정보와 출처는 미확인입니다. 담당자 수락으로 간주하지 않습니다."
VALID_CATEGORIES = {"benefit", "vaccination_checkup", "regular_visit"}
VALID_STATUSES = {"확인 필요", "담당 요청", "진행 중", "완료", "해당 없음"}


class DatabaseUnavailable(Exception):
    pass


def postgres_engine():
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise DatabaseUnavailable()
    url = URL.create(
        "postgresql+psycopg",
        username="postgres",
        password=password,
        host="postgres",
        port=5432,
        database="postgres",
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )


def seed_task(row):
    task_id = str(row["task_id"] or "").strip()
    title = str(row["title"] or "").strip()
    description = str(row["description"] or "").strip()
    category = str(row["category"] or "").strip()
    status = str(row["status"] or "").strip()
    if (
        not task_id or len(task_id) > 100 or not title or len(title) > 200
        or not description or category not in VALID_CATEGORIES or status not in VALID_STATUSES
    ):
        raise DatabaseUnavailable()
    due_date = row["due_date"]
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    elif due_date and not isinstance(due_date, date):
        try:
            due_date = date.fromisoformat(str(due_date))
        except ValueError:
            raise DatabaseUnavailable() from None
    elif not due_date:
        due_date = None
    return {
        "task_id": task_id,
        "title": title,
        "description": f"{SEED_NOTICE}\n{description}",
        "category": category,
        "due_date": due_date,
        "status": "확인 필요" if status == "담당 요청" else status,
        "assignee_id": None,
        "requested_assignee_id": None,
        "assignment_status": "unassigned",
        "source_id": None,
    }


class Database:
    def __init__(self, engine=None):
        self._engine = engine
        self._ready = False
        self._lock = threading.Lock()

    def ensure_ready(self):
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            if self._engine is None:
                self._engine = postgres_engine()
            with self._engine.begin() as connection:
                if connection.dialect.name == "postgresql":
                    connection.execute(text("SELECT pg_advisory_xact_lock(1729104512)"))
                metadata.create_all(connection)
                marker = connection.execute(
                    select(seed_markers.c.name).where(seed_markers.c.name == SEED_MARKER)
                ).first()
                if marker is None:
                    existing_ids = set(connection.execute(select(tasks.c.task_id)).scalars())
                    rows = connection.execute(
                        text(
                            "SELECT task_id, title, description, category, due_date, status "
                            "FROM public.chengdo_table"
                        )
                    ).mappings()
                    for row in rows:
                        task = seed_task(row)
                        if task["task_id"] not in existing_ids:
                            connection.execute(insert(tasks).values(**task))
                            existing_ids.add(task["task_id"])
                    connection.execute(insert(seed_markers).values(name=SEED_MARKER))
            self._ready = True

    @contextmanager
    def transaction(self):
        self.ensure_ready()
        with self._engine.begin() as connection:
            yield connection
