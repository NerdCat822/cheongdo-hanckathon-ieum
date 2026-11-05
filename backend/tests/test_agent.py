import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from copilot.generated.session_events import AssistantMessageData, SessionEvent, SessionEventType
from copilot.generated.session_events import PermissionRequestCustomTool, PermissionRequestRead
from copilot.generated.rpc import PermissionDecisionApproveOnce, PermissionDecisionReject
from copilot.tools import ToolInvocation

from backend.agent import AgentBusy, AgentInvalidResponse, AgentUnavailable, CopilotDraftService, parse_response, source_permission


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
        self.stopped = False
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
        self.stopped = True

    async def get_auth_status(self):
        return SimpleNamespace(isAuthenticated=True)

    async def create_session(self, **options):
        self.session_options = options
        return FakeSession(self, options)

    async def delete_session(self, session_id):
        self.deleted.append(session_id)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_framework_bridge_calls_sdk_tool_and_cleans_up(self):
        with patch.dict(os.environ, {"CARE_AI_ENABLED": "true", "COPILOT_GITHUB_TOKEN": "fake-oauth"}, clear=False):
            with patch("backend.agent.CopilotClient", FakeClient):
                result = await CopilotDraftService().generate("benefit")
        client = FakeClient.instance
        self.assertEqual(client.options["mode"], "empty")
        self.assertFalse(client.options["use_logged_in_user"])
        self.assertEqual(client.session_options["available_tools"], ["custom:lookup_care_source"])
        self.assertFalse(client.session_options["enable_file_hooks"])
        permission = PermissionRequestCustomTool(tool_description="source", tool_name="lookup_care_source", args={})
        self.assertIsInstance(await client.session_options["on_permission_request"](permission, {}), PermissionDecisionApproveOnce)
        self.assertEqual(client.tool_result.result_type, "success")
        self.assertIn("보건복지부", client.tool_result.text_result_for_llm)
        self.assertTrue(client.stopped)
        self.assertFalse(os.path.exists(client.options["base_directory"]))
        self.assertEqual(result["drafts"][0]["source_id"], "benefit")
        self.assertEqual(result["source"]["provider"], "보건복지부")

    async def test_missing_source_tool_rejects_output_and_cleans_up(self):
        with patch.dict(os.environ, {"CARE_AI_ENABLED": "true", "COPILOT_GITHUB_TOKEN": "fake-oauth"}, clear=False):
            with patch("backend.agent.CopilotClient", FakeClient), patch.object(FakeClient, "call_tool", False):
                with self.assertRaises(AgentInvalidResponse):
                    await CopilotDraftService().generate("benefit")
        self.assertTrue(FakeClient.instance.stopped)
        self.assertFalse(os.path.exists(FakeClient.instance.options["base_directory"]))

    async def test_vaccination_draft_uses_live_public_source_as_evidence(self):
        class FakePublicData:
            async def vaccines(self):
                return {
                    "source": {"title": "질병관리청", "url": "https://www.data.go.kr/data/15084296/openapi.do"},
                    "retrieved_at": "2026-11-05T00:00:00+00:00",
                    "items": [{"code": "01", "name": "결핵"}],
                }

        with patch.dict(os.environ, {"CARE_AI_ENABLED": "true", "COPILOT_GITHUB_TOKEN": "fake-oauth"}, clear=False):
            with patch("backend.agent.CopilotClient", FakeClient):
                result = await CopilotDraftService(FakePublicData()).generate("vaccination_checkup")
        self.assertEqual(result["evidence"]["items"], [{"code": "01", "name": "결핵"}])
        self.assertEqual(result["evidence"]["retrieved_at"], "2026-11-05T00:00:00+00:00")
        self.assertIn("결핵", FakeClient.instance.tool_result.text_result_for_llm)

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

    def test_only_the_read_only_source_tool_can_be_approved(self):
        source = PermissionRequestCustomTool(tool_description="source", tool_name="lookup_care_source", args={})
        self.assertIsInstance(source_permission(source, {}), PermissionDecisionApproveOnce)
        for request in (
            PermissionRequestCustomTool(tool_description="x", tool_name="other", args={}),
            PermissionRequestCustomTool(tool_description="x", tool_name="lookup_care_source", args={"path": "/"}),
            PermissionRequestCustomTool(tool_description="x", tool_name="lookup_care_source", args={}, managed_approval_required=True),
            PermissionRequestRead(path="/tmp", intention="read"),
        ):
            with self.subTest(request=request):
                self.assertIsInstance(source_permission(request, {}), PermissionDecisionReject)
