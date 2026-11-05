from uuid import uuid4

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from backend.catalog import MEMBERS, PROFILE, SOURCES
from backend.database import Database, DatabaseUnavailable, tasks
from backend.schemas import AssignmentRequest, AssignmentResponse, DraftRequest, TaskCreate, TaskPatch

DEMO_WARNING = (
    "인증·동의·권한 검증이 없는 공개 가상 시연입니다. "
    "실제 개인정보나 건강정보를 입력하지 마세요. 운영용 서비스가 아닙니다."
)
AGENT_REASON = "시연 환경에서 검증된 AI 제공자가 없어 초안을 만들거나 외부 전송하지 않습니다."
JIRA_REASON = "공개 시연에서는 인증과 승인 절차가 검증되지 않아 Jira를 사용하지 않습니다."
KNOWN_FIELDS = {
    "body", "path", "query", "task_id", "title", "description", "category", "due_date",
    "status", "source_id", "assignee_id", "member_id", "decision", "prompt",
}


def create_app(database=None):
    app = FastAPI(title="가상 가족 돌봄 시연 API", description=DEMO_WARNING, version="1.0")
    app.state.database = database if database is not None else Database()

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            location = [part if isinstance(part, str) and part in KNOWN_FIELDS else "unknown"
                        for part in error["loc"]]
            errors.append({"loc": location, "msg": "유효하지 않거나 누락된 입력입니다.", "type": error["type"]})
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(DatabaseUnavailable)
    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=503,
            content={"detail": "시연 데이터베이스를 사용할 수 없습니다. 연결과 초기 데이터를 확인하세요."},
        )

    def find_task(connection, task_id, *, lock=False):
        query = select(tasks).where(tasks.c.task_id == task_id)
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="시연 업무를 찾을 수 없습니다.")
        return dict(row)

    @app.get("/api/health")
    def health():
        with app.state.database.transaction() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        return {"status": "ok"}

    @app.get("/api/demo")
    def demo():
        with app.state.database.transaction() as connection:
            rows = connection.execute(select(tasks).order_by(tasks.c.task_id)).mappings().all()
            return {"profile": PROFILE, "members": MEMBERS, "tasks": [dict(row) for row in rows], "sources": SOURCES}

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: TaskCreate):
        task = {
            "task_id": f"TASK-{uuid4().hex}",
            **payload.model_dump(),
            "status": "확인 필요",
            "assignee_id": None,
            "requested_assignee_id": None,
            "assignment_status": "unassigned",
        }
        with app.state.database.transaction() as connection:
            connection.execute(insert(tasks).values(**task))
        return task

    @app.patch("/api/tasks/{task_id}")
    def patch_task(payload: TaskPatch, task_id: str = Path(min_length=1, max_length=100)):
        changes = payload.model_dump(exclude_unset=True)
        with app.state.database.transaction() as connection:
            task = find_task(connection, task_id, lock=True)
            if "status" in changes:
                status = changes["status"]
                if status == "담당 요청" and task["assignment_status"] != "pending":
                    raise HTTPException(status_code=409, detail="담당 요청은 별도 요청 절차로 만들어야 합니다.")
                if status != "담당 요청" and task["assignment_status"] == "pending":
                    raise HTTPException(status_code=409, detail="대기 중인 담당 요청을 먼저 응답해 주세요.")
            connection.execute(update(tasks).where(tasks.c.task_id == task_id).values(**changes))
            return find_task(connection, task_id)

    @app.post("/api/tasks/{task_id}/assignment-request")
    def request_assignment(payload: AssignmentRequest, task_id: str = Path(min_length=1, max_length=100)):
        with app.state.database.transaction() as connection:
            task = find_task(connection, task_id, lock=True)
            if task["assignment_status"] == "pending":
                if task["requested_assignee_id"] == payload.assignee_id:
                    return task
                raise HTTPException(status_code=409, detail="다른 가상 구성원의 응답을 기다리고 있습니다.")
            if task["status"] in {"완료", "해당 없음"}:
                raise HTTPException(status_code=409, detail="완료 또는 해당 없음 업무에는 담당을 요청할 수 없습니다.")
            connection.execute(
                update(tasks).where(tasks.c.task_id == task_id).values(
                    status="담당 요청",
                    assignee_id=None,
                    requested_assignee_id=payload.assignee_id,
                    assignment_status="pending",
                )
            )
            return find_task(connection, task_id)

    @app.post("/api/tasks/{task_id}/assignment-response")
    def respond_assignment(payload: AssignmentResponse, task_id: str = Path(min_length=1, max_length=100)):
        with app.state.database.transaction() as connection:
            task = find_task(connection, task_id, lock=True)
            if task["assignment_status"] != "pending":
                raise HTTPException(status_code=409, detail="응답할 대기 중인 담당 요청이 없습니다.")
            if task["requested_assignee_id"] != payload.member_id:
                raise HTTPException(status_code=403, detail="요청받은 가상 구성원만 응답할 수 있습니다.")
            accepted = payload.decision == "accept"
            connection.execute(
                update(tasks).where(tasks.c.task_id == task_id).values(
                    status="진행 중" if accepted else "확인 필요",
                    assignee_id=payload.member_id if accepted else None,
                    requested_assignee_id=None,
                    assignment_status="accepted" if accepted else "unassigned",
                )
            )
            return find_task(connection, task_id)

    @app.get("/api/integrations")
    def integrations():
        return {
            "agent": {"available": False, "reason": AGENT_REASON},
            "jira": {"available": False, "reason": JIRA_REASON},
        }

    @app.post("/api/agent/draft")
    def agent_draft(_payload: DraftRequest):
        raise HTTPException(status_code=503, detail=AGENT_REASON)

    return app


app = create_app()
