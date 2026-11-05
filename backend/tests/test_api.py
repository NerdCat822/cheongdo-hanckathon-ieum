import logging
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.database import Database, SEED_NOTICE, metadata


TASK_FIELDS = {
    "task_id", "title", "description", "category", "due_date", "status",
    "assignee_id", "requested_assignee_id", "assignment_status", "source_id",
}


def make_engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_public(dbapi_connection, _record):
        dbapi_connection.execute("ATTACH DATABASE ':memory:' AS public")

    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE public.chengdo_table ("
            "task_id TEXT, title TEXT, description TEXT, category TEXT, "
            "due_date TEXT, status TEXT, assignee_id TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO public.chengdo_table VALUES "
            "('seed-1', '가상 확인', '가상 업무 설명', 'benefit', '2026-11-05', '진행 중', 'unverified')"
        ))
        connection.execute(text(
            "INSERT INTO public.chengdo_table VALUES "
            "('seed-2', '가상 요청', '가상 업무 설명', 'regular_visit', NULL, '담당 요청', 'unverified')"
        ))
    return engine


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.client = TestClient(create_app(Database(self.engine)))
        self.client.__enter__()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.client.__exit__, None, None, None)

    def create_task(self):
        response = self.client.post("/api/tasks", json={
            "title": "가상 방문",
            "description": "가상 안부 확인",
            "category": "regular_visit",
            "due_date": "2026-12-01",
            "source_id": "regular_visit",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(set(response.json()), TASK_FIELDS)
        return response.json()["task_id"]

    def test_health_demo_shapes_and_unverified_import(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        response = self.client.get("/api/demo")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"profile", "members", "tasks", "sources"})
        self.assertEqual(set(data["profile"]), {"alias", "region"})
        self.assertIn("시연", data["profile"]["alias"])
        self.assertTrue(all(set(m) == {"id", "name"} for m in data["members"]))
        self.assertTrue(all(set(s) == {"id", "title", "provider", "url", "checked_at", "summary"}
                            for s in data["sources"]))
        self.assertEqual(len(data["tasks"]), 2)
        for task in data["tasks"]:
            self.assertEqual(set(task), TASK_FIELDS)
            self.assertIn(SEED_NOTICE, task["description"])
            self.assertEqual(task["assignment_status"], "unassigned")
            self.assertIsNone(task["assignee_id"])
            self.assertIsNone(task["requested_assignee_id"])
            self.assertIsNone(task["source_id"])
        self.assertEqual(data["tasks"][1]["status"], "확인 필요")

    def test_seed_once_and_persistence_across_app_restart(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        task_id = self.create_task()
        self.assertEqual(
            self.client.patch("/api/tasks/seed-1", json={"title": "가상 수정"}).status_code, 200
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO public.chengdo_table VALUES "
                "('seed-3', '추가된 원본', '가상 업무', 'benefit', NULL, '확인 필요', NULL)"
            ))
            original = connection.execute(
                text("SELECT title FROM public.chengdo_table WHERE task_id = 'seed-1'")
            ).scalar_one()
        self.assertEqual(original, "가상 확인")
        with TestClient(create_app(Database(self.engine))) as restarted:
            saved = {task["task_id"]: task for task in restarted.get("/api/demo").json()["tasks"]}
        self.assertIn(task_id, saved)
        self.assertEqual(saved["seed-1"]["title"], "가상 수정")
        self.assertNotIn("seed-3", saved)

    def test_seed_does_not_overwrite_existing_demo_rows(self):
        with self.engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(text(
                "INSERT INTO care_demo_tasks "
                "(task_id, title, description, category, status, assignment_status) VALUES "
                "('seed-1', '기존 가상 수정', '가상 설명', 'benefit', '확인 필요', 'unassigned')"
            ))
        response = self.client.get("/api/demo")
        self.assertEqual(response.status_code, 200, response.text)
        seeded = {task["task_id"]: task for task in response.json()["tasks"]}
        self.assertEqual(seeded["seed-1"]["title"], "기존 가상 수정")
        self.assertIn("seed-2", seeded)

    def test_task_creation_patch_and_sql_parameters(self):
        task_id = self.create_task()
        response = self.client.patch(f"/api/tasks/{task_id}", json={
            "title": "'; DROP TABLE care_demo_tasks; --",
            "category": "benefit",
            "due_date": None,
            "source_id": None,
            "status": "완료",
        })
        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()
        self.assertEqual(task["title"], "'; DROP TABLE care_demo_tasks; --")
        self.assertEqual(task["category"], "benefit")
        self.assertIsNone(task["due_date"])
        self.assertIsNone(task["source_id"])
        self.assertEqual(task["status"], "완료")
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(
            self.client.post(f"/api/tasks/{task_id}/assignment-request",
                             json={"assignee_id": "member-1"}).status_code, 409
        )

    def test_accept_requires_recipient_and_pending_request(self):
        task_id = self.create_task()
        request_url = f"/api/tasks/{task_id}/assignment-request"
        response_url = f"/api/tasks/{task_id}/assignment-response"
        self.assertEqual(self.client.post(response_url, json={
            "member_id": "member-1", "decision": "accept"
        }).status_code, 409)
        pending = self.client.post(request_url, json={"assignee_id": "member-1"}).json()
        self.assertEqual(pending["status"], "담당 요청")
        self.assertEqual(pending["assignment_status"], "pending")
        self.assertEqual(pending["requested_assignee_id"], "member-1")
        self.assertIsNone(pending["assignee_id"])
        self.assertEqual(self.client.post(request_url, json={"assignee_id": "member-1"}).json(), pending)
        self.assertEqual(self.client.post(request_url, json={"assignee_id": "member-2"}).status_code, 409)
        self.assertEqual(self.client.patch(f"/api/tasks/{task_id}", json={"status": "완료"}).status_code, 409)
        self.assertEqual(self.client.post(response_url, json={
            "member_id": "member-2", "decision": "accept"
        }).status_code, 403)
        accepted = self.client.post(response_url, json={
            "member_id": "member-1", "decision": "accept"
        }).json()
        self.assertEqual(accepted["status"], "진행 중")
        self.assertEqual(accepted["assignment_status"], "accepted")
        self.assertEqual(accepted["assignee_id"], "member-1")
        self.assertIsNone(accepted["requested_assignee_id"])
        self.assertEqual(self.client.post(response_url, json={
            "member_id": "member-1", "decision": "accept"
        }).status_code, 409)
        pending_again = self.client.post(request_url, json={"assignee_id": "member-2"}).json()
        self.assertEqual(pending_again["assignment_status"], "pending")
        self.assertIsNone(pending_again["assignee_id"])

    def test_reject_and_adjust_leave_unassigned(self):
        for decision in ("reject", "adjust"):
            with self.subTest(decision=decision):
                task_id = self.create_task()
                base = f"/api/tasks/{task_id}"
                self.client.post(base + "/assignment-request", json={"assignee_id": "member-3"})
                task = self.client.post(base + "/assignment-response", json={
                    "member_id": "member-3", "decision": decision
                }).json()
                self.assertEqual(task["status"], "확인 필요")
                self.assertEqual(task["assignment_status"], "unassigned")
                self.assertIsNone(task["assignee_id"])
                self.assertIsNone(task["requested_assignee_id"])

    def test_invalid_missing_fields_and_unavailable_tasks(self):
        task_id = self.create_task()
        for payload in (
            {}, {"title": "x", "description": "y"},
            {"title": "", "description": "y", "category": "benefit"},
            {"title": None, "description": "y", "category": "benefit"},
            {"title": "x", "description": "y", "category": "other"},
            {"title": "x", "description": "y", "category": "benefit", "due_date": "2026-02-30"},
            {"title": "x", "description": "y", "category": "benefit", "due_date": 42},
            {"title": "x", "description": "y", "category": "benefit", "source_id": "invalid"},
            {"title": "x", "description": "y", "category": "benefit", "assignee_id": "member-1"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/tasks", json=payload)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("detail", response.json())
        for payload in ({}, {"title": None}, {"status": None}, {"status": "other"}, {"extra": "x"}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch(f"/api/tasks/{task_id}", json=payload).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/tasks/{task_id}", json={"status": "담당 요청"}).status_code, 409)
        self.assertEqual(self.client.patch("/api/tasks/missing", json={"title": "x"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/tasks/{task_id}/assignment-request",
                                          json={"assignee_id": "not-a-member"}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/tasks/{task_id}/assignment-response",
                                          json={"member_id": "member-1", "decision": "maybe"}).status_code, 422)

    def test_integrations_do_not_generate_store_or_send_prompt(self):
        marker = "가상-프롬프트-출력-금지"
        captured = []

        class Capture(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())

        handler = Capture()
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        with patch("socket.socket.connect", side_effect=AssertionError("unexpected network")):
            integrations = self.client.get("/api/integrations").json()
            self.assertEqual(set(integrations), {"agent", "jira"})
            for value in integrations.values():
                self.assertEqual(set(value), {"available", "reason"})
                self.assertIs(value["available"], False)
                self.assertTrue(value["reason"])
            before = self.client.get("/api/demo").json()["tasks"]
            response = self.client.post("/api/agent/draft", json={"prompt": marker})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(marker, response.text)
            invalid = self.client.post("/api/agent/draft", json={"prompt": marker, marker: marker})
            self.assertEqual(invalid.status_code, 422)
            self.assertNotIn(marker, invalid.text)
            self.assertEqual(before, self.client.get("/api/demo").json()["tasks"])
            self.assertEqual(self.client.post("/api/jira/tickets", json={}).status_code, 404)
        self.assertNotIn(marker, "\n".join(captured))

    def test_failed_initialization_is_not_marked_and_can_recover(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE public.chengdo_table"))
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("SELECT", response.text)
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE public.chengdo_table ("
                "task_id TEXT, title TEXT, description TEXT, category TEXT, due_date TEXT, status TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO public.chengdo_table VALUES "
                "('retry', '가상 업무', '가상 설명', 'benefit', NULL, '확인 필요')"
            ))
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/demo").json()["tasks"][0]["task_id"], "retry")


if __name__ == "__main__":
    unittest.main()
