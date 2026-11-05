"""선택 사항: 별도 로컬 PostgreSQL에 가상 데이터만 넣어 검증한다."""

import os
import shutil
import socket
import subprocess
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from backend.app import create_app
from backend.database import Database

BIN_DIR = os.environ.get("CARE_DEMO_TEST_POSTGRES_BIN")


@unittest.skipUnless(BIN_DIR, "격리된 PostgreSQL 테스트 실행 파일 경로가 지정되지 않았습니다.")
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bin_dir = Path(BIN_DIR).resolve()
        cls.scratch = Path(__file__).resolve().parent / (".postgres-test-" + uuid4().hex)
        cls.scratch.mkdir()
        cls.data_dir = cls.scratch / "data"
        cls.environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(cls.scratch),
            "TMPDIR": str(cls.scratch),
            "LC_ALL": "C",
        }
        library_dir = os.environ.get("CARE_DEMO_TEST_POSTGRES_LIB")
        if library_dir:
            cls.environment["LD_LIBRARY_PATH"] = library_dir
        cls.process = None
        cls.log = None
        try:
            subprocess.run(
                [str(cls.bin_dir / "initdb"), "-D", str(cls.data_dir), "-U", "postgres",
                 "--auth=trust", "--encoding=UTF8", "--no-instructions"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=cls.environment,
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                cls.port = sock.getsockname()[1]
            cls.start_postgres()
            cls.engine = create_engine(
                URL.create("postgresql+psycopg", username="postgres", host="127.0.0.1",
                           port=cls.port, database="postgres"),
                pool_pre_ping=True,
                connect_args={"connect_timeout": 2},
            )
        except Exception:
            cls.stop_postgres()
            shutil.rmtree(cls.scratch, ignore_errors=True)
            raise

    @classmethod
    def start_postgres(cls):
        cls.log = (cls.scratch / "postgres.log").open("ab")
        cls.process = subprocess.Popen(
            [str(cls.bin_dir / "postgres"), "-D", str(cls.data_dir),
             "-c", "listen_addresses=127.0.0.1", "-c", f"port={cls.port}",
             "-c", "unix_socket_directories=", "-c", "fsync=off"],
            env=cls.environment, stdout=cls.log, stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            if cls.process.poll() is not None:
                details = (cls.scratch / "postgres.log").read_text(encoding="utf-8", errors="replace")
                raise RuntimeError("격리된 PostgreSQL을 시작하지 못했습니다: " + details[-2000:])
            try:
                with psycopg.connect(host="127.0.0.1", port=cls.port, user="postgres",
                                     dbname="postgres", connect_timeout=1):
                    return
            except psycopg.OperationalError:
                time.sleep(0.1)
        raise RuntimeError("격리된 PostgreSQL 시작 시간이 초과되었습니다.")

    @classmethod
    def stop_postgres(cls):
        if cls.process is not None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=10)
            cls.process = None
        if cls.log is not None:
            cls.log.close()
            cls.log = None

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.stop_postgres()
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS care_demo_tasks, care_demo_seed_markers"))
            connection.execute(text("DROP TABLE IF EXISTS public.chengdo_table"))
            connection.execute(text(
                "CREATE TABLE public.chengdo_table ("
                "task_id TEXT, title TEXT, description TEXT, category TEXT, due_date DATE, "
                "status TEXT, assignee_id TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO public.chengdo_table VALUES "
                "('seed-1', '가상 업무', '가상 설명', 'benefit', '2026-11-05', '진행 중', '미확인')"
            ))

    def test_concurrent_seed_initialization_and_database_restart(self):
        barrier = threading.Barrier(8)

        def initialize(_):
            client = TestClient(create_app(Database(self.engine)))
            barrier.wait(timeout=10)
            with client:
                response = client.get("/api/demo")
                return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(initialize, range(8)))
        self.assertTrue(all(status == 200 and len(data["tasks"]) == 1 for status, data in results))
        with self.engine.begin() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM care_demo_tasks")).scalar_one(), 1)
            self.assertEqual(connection.execute(text("SELECT count(*) FROM care_demo_seed_markers")).scalar_one(), 1)

        database = Database(self.engine)
        with TestClient(create_app(database)) as client:
            created = client.post("/api/tasks", json={
                "title": "가상 저장", "description": "가상 설명", "category": "benefit"
            }).json()
            self.engine.dispose()
            self.stop_postgres()
            self.start_postgres()
            response = client.get("/api/demo")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn(created["task_id"], [task["task_id"] for task in response.json()["tasks"]])
        with self.engine.begin() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM public.chengdo_table")).scalar_one(), 1)

    def test_concurrent_responses_only_one_wins(self):
        app = create_app(Database(self.engine))
        with TestClient(app) as client:
            task_id = client.post("/api/tasks", json={
                "title": "가상 업무", "description": "가상 설명", "category": "benefit"
            }).json()["task_id"]
            base = f"/api/tasks/{task_id}"
            self.assertEqual(client.post(base + "/assignment-request",
                                         json={"assignee_id": "member-1"}).status_code, 200)
            barrier = threading.Barrier(2)

            def respond(decision):
                barrier.wait(timeout=10)
                response = client.post(base + "/assignment-response",
                                       json={"member_id": "member-1", "decision": decision})
                return response.status_code

            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(respond, ("accept", "reject")))
            self.assertEqual(sorted(statuses), [200, 409])
            task = next(item for item in client.get("/api/demo").json()["tasks"] if item["task_id"] == task_id)
            self.assertIn(task["assignment_status"], ("accepted", "unassigned"))
            self.assertIsNone(task["requested_assignee_id"])


if __name__ == "__main__":
    unittest.main()
