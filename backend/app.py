import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agent_framework.exceptions import AgentException
from copilot._jsonrpc import JsonRpcError, ProcessExitedError
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from backend.agent import AgentBusy, AgentInvalidResponse, AgentUnavailable, CopilotDraftService
from backend.catalog import MEMBERS, PROFILE, SOURCES
from backend.database import Database, DatabaseUnavailable, ai_usage, task_activity, tasks
from backend.public_data import PublicDataBusy, PublicDataError, PublicDataService, PublicDataUnavailable
from backend.schemas import AssignmentRequest, AssignmentResponse, DraftRequest, HospitalDetailRequest, HospitalSearch, TaskCreate, TaskPatch

DEMO_WARNING = (
    "인증·동의·권한 검증이 없는 공개 가상 시연입니다. "
    "실제 개인정보나 건강정보를 입력하지 마세요. 운영용 서비스가 아닙니다."
)
AGENT_REASON = "Copilot 인증과 AI 사용 설정이 필요합니다."
logger = logging.getLogger(__name__)
KNOWN_FIELDS = {
    "body", "path", "query", "task_id", "title", "description", "category", "due_date",
    "status", "source_id", "assignee_id", "member_id", "decision", "category", "acknowledged",
}


def create_app(database=None, draft_service=None, public_data_service=None):
    app = FastAPI(title="가상 가족 돌봄 시연 API", description=DEMO_WARNING, version="1.0")
    app.state.database = database if database is not None else Database()
    app.state.draft_service = draft_service if draft_service is not None else CopilotDraftService()
    app.state.public_data = public_data_service if public_data_service is not None else PublicDataService()
    app.state.ai_daily_limit = 10

    def record_activity(connection, task_id, kind, detail):
        connection.execute(insert(task_activity).values(
            event_id=uuid4().hex,
            task_id=task_id,
            kind=kind,
            detail=detail,
            created_at=datetime.now(timezone.utc),
        ))

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

    @app.exception_handler(PublicDataUnavailable)
    async def public_data_unavailable(_request: Request, _exc: PublicDataUnavailable):
        return JSONResponse(status_code=503, content={"detail": "공공데이터 API 이용 승인과 인증 설정이 필요합니다."})

    @app.exception_handler(PublicDataError)
    async def public_data_error(_request: Request, _exc: PublicDataError):
        return JSONResponse(status_code=502, content={"detail": "공공데이터를 조회하지 못했습니다. 잠시 후 다시 시도해 주세요."})

    @app.exception_handler(PublicDataBusy)
    async def public_data_busy(_request: Request, _exc: PublicDataBusy):
        return JSONResponse(status_code=429, content={"detail": "공공데이터 요청이 많습니다. 잠시 후 다시 시도해 주세요."})

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
            record_activity(connection, task["task_id"], "created", "할 일을 만들었습니다.")
        return task

    @app.get("/api/tasks/{task_id}/activity")
    def get_activity(task_id: str = Path(min_length=1, max_length=100)):
        with app.state.database.transaction() as connection:
            find_task(connection, task_id)
            rows = connection.execute(
                select(task_activity).where(task_activity.c.task_id == task_id)
                .order_by(task_activity.c.created_at.desc(), task_activity.c.event_id.desc()).limit(100)
            ).mappings().all()
            return [dict(row) for row in rows]

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
            if "status" in changes and changes["status"] != task["status"]:
                record_activity(connection, task_id, "status", f"상태: {task['status']} → {changes['status']}")
            if any(key != "status" and value != task[key] for key, value in changes.items()):
                record_activity(connection, task_id, "edited", "할 일 내용을 수정했습니다.")
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
            member_name = next(member["name"] for member in MEMBERS if member["id"] == payload.assignee_id)
            record_activity(connection, task_id, "requested", f"{member_name}에게 담당을 요청했습니다.")
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
            member_name = next(member["name"] for member in MEMBERS if member["id"] == payload.member_id)
            decision = {"accept": "수락", "reject": "거절", "adjust": "조정"}[payload.decision]
            record_activity(connection, task_id, "response", f"{member_name}: 담당 요청 {decision}")
            return find_task(connection, task_id)

    @app.get("/api/integrations")
    def integrations():
        return {
            "agent": {
                "available": app.state.draft_service.available,
                "reason": "Copilot 설정됨. 초안 생성 시 인증을 확인합니다."
                if app.state.draft_service.available else AGENT_REASON,
            },
            "jira": {"available": False, "reason": "외부 Jira 대신 자체 업무 보드를 사용합니다."},
        }

    @app.post("/api/agent/draft")
    async def agent_draft(payload: DraftRequest):
        if not app.state.draft_service.available:
            raise HTTPException(status_code=503, detail=AGENT_REASON)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=1)
        with app.state.database.transaction() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(1729104513)"))
            connection.execute(delete(ai_usage).where(ai_usage.c.created_at < cutoff))
            count = connection.execute(select(func.count()).select_from(ai_usage)).scalar_one()
            if count >= app.state.ai_daily_limit:
                raise HTTPException(status_code=429, detail="공개 시연의 AI 하루 요청 한도에 도달했습니다.")
            connection.execute(insert(ai_usage).values(request_id=uuid4().hex, created_at=now))
        try:
            return await app.state.draft_service.generate(payload.category)
        except AgentBusy:
            raise HTTPException(status_code=429, detail="AI 요청이 많습니다. 잠시 후 다시 시도해 주세요.") from None
        except AgentInvalidResponse:
            raise HTTPException(status_code=502, detail="AI 초안이나 출처 확인에 실패했습니다. 다시 시도해 주세요.") from None
        except AgentUnavailable:
            raise HTTPException(status_code=503, detail=AGENT_REASON) from None
        except (AgentException, JsonRpcError, ProcessExitedError, OSError, RuntimeError) as exc:
            logger.warning("Copilot draft failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Copilot 연결에 실패했습니다. 인증과 모델 설정을 확인해 주세요.") from None

    @app.post("/api/public/hospitals")
    async def hospitals(payload: HospitalSearch):
        return await app.state.public_data.hospitals(payload.name)

    @app.post("/api/public/hospital-specialties")
    async def hospital_specialties(payload: HospitalDetailRequest):
        return await app.state.public_data.hospital_specialties(payload.hospital_id)

    @app.get("/api/public/vaccines")
    async def vaccines():
        return await app.state.public_data.vaccines()

    @app.get("/api/public/vaccines/{code}")
    async def vaccine_detail(code: str = Path(pattern=r"^[0-9]{2}$")):
        return await app.state.public_data.vaccine_detail(code)

    return app


app = create_app()
