import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from copilot.generated.session_events import AssistantMessageData, SessionEvent, SessionEventType
from copilot.tools import ToolInvocation

from backend.agent import AgentBusy, AgentInvalidResponse, AgentUnavailable, CopilotDraftService, parse_response


class FakeSession:
    def __init__(self, client, options):
        self.client = client
        self.options = options
        self.session_id = "test-session"

    def on(self, _handler):
        return lambda: None

    async def send_and_wait(self, _prompt, **_kwargs):
        if self.client.call_tool:
            result = await self.options["tools"][0].handler(ToolInvocation(
                session_id=self.session_id, tool_call_id="test-call",
                tool_name="lookup_care_source", arguments={},
            ))
            self.client.tool_result = result
        return SessionEvent(
            id=uuid4(), timestamp=datetime.now(timezone.utc), type=SessionEventType.ASSISTANT_MESSAGE,
            data=AssistantMessageData(
                content='{"drafts":[{"title":"가상 안내 확인","description":"기관에 안내를 확인한다.","uncertainty":"세부 조건은 기관에 확인한다."}]}',
                message_id="test-message",
            ),
        )


class FakeClient:
    instance = None
    call_tool = True

    def __init__(self, **options):
        self.options = options
        self.session_options = None
        self.deleted = []
        self.tool_result = None
        FakeClient.instance = self

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_args):
        await self.stop()

    async def start(self):
        pass

    async def stop(self):
        pass

    async def get_auth_status(self):
        return SimpleNamespace(isAuthenticated=True)

    async def create_session(self, **options):
        self.session_options = options
        return FakeSession(self, options)

    async def delete_session(self, session_id):
        self.deleted.append(session_id)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_framework_bridge_calls_sdk_tool_and_removes_session(self):
        with patch.dict(os.environ, {"CARE_AI_ENABLED": "true", "COPILOT_GITHUB_TOKEN": "fake-oauth"}, clear=False):
            with patch("backend.agent.CopilotClient", FakeClient):
                result = await CopilotDraftService().generate("benefit")
        client = FakeClient.instance
        self.assertEqual(client.options["mode"], "empty")
        self.assertFalse(client.options["use_logged_in_user"])
        self.assertEqual(client.session_options["available_tools"], ["custom:lookup_care_source"])
        self.assertFalse(client.session_options["enable_file_hooks"])
        self.assertEqual(client.tool_result.result_type, "success")
        self.assertIn("보건복지부", client.tool_result.text_result_for_llm)
        self.assertEqual(client.deleted, ["test-session"])
        self.assertEqual(result["drafts"][0]["source_id"], "benefit")
        self.assertEqual(result["source"]["provider"], "보건복지부")

    async def test_missing_source_tool_rejects_output_and_cleans_up(self):
        with patch.dict(os.environ, {"CARE_AI_ENABLED": "true", "COPILOT_GITHUB_TOKEN": "fake-oauth"}, clear=False):
            with patch("backend.agent.CopilotClient", FakeClient), patch.object(FakeClient, "call_tool", False):
                with self.assertRaises(AgentInvalidResponse):
                    await CopilotDraftService().generate("benefit")
        self.assertEqual(FakeClient.instance.deleted, ["test-session"])

    async def test_disabled_and_rate_limited(self):
        with patch.dict(os.environ, {"CARE_AI_ENABLED": "false", "COPILOT_GITHUB_TOKEN": ""}):
            with self.assertRaises(AgentUnavailable):
                await CopilotDraftService().generate("benefit")
        with patch.dict(os.environ, {"CARE_AI_ENABLED": "true", "COPILOT_GITHUB_TOKEN": "fake"}):
            service = CopilotDraftService()
            service._running = True
            with self.assertRaises(AgentBusy):
                await service.generate("benefit")

    def test_strict_output_validation(self):
        valid = '```json\n{"drafts":[{"title":"확인","description":"기관 확인","uncertainty":"기관 확인 필요"}]}\n```'
        self.assertEqual(parse_response(valid).drafts[0].title, "확인")
        for invalid in (
            "not json", '{"drafts":[]}', '{"drafts":[{"title":"x","description":"y","uncertainty":"z","source_id":"invented"}]}',
            '{"drafts":[{"title":"","description":"y","uncertainty":"z"}]}',
        ):
            with self.subTest(invalid=invalid), self.assertRaises(AgentInvalidResponse):
                parse_response(invalid)
