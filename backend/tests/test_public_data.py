import os
import unittest
from unittest.mock import patch

import httpx

from backend.public_data import PublicDataError, PublicDataService, PublicDataUnavailable


def xml(items, code="00"):
    return f"<response><header><resultCode>{code}</resultCode></header><body><items>{items}</items></body></response>"


class PublicDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_operation_paths_and_decoded_parameters(self):
        requests = []

        def respond(request):
            requests.append(request)
            path = request.url.path
            if path.endswith("getHospBasisList"):
                return httpx.Response(200, text=xml("<item><ykiho>abc+/=</ykiho><yadmNm>가상병원</yadmNm><addr>가상주소</addr><telno>123</telno><clCdNm>병원</clCdNm></item>"))
            if path.endswith("getDgsbjtInfo2.8"):
                return httpx.Response(200, text=xml("<item><dgsbjtCdNm>내과</dgsbjtCdNm><dgsbjtPrSdrCnt>1</dgsbjtPrSdrCnt></item>"))
            if path.endswith("getCondVcnCd"):
                return httpx.Response(200, text=xml("<item><cd>01</cd><cdNm>결핵</cdNm></item>"))
            return httpx.Response(200, text=xml("<item><title>가상 감염병</title><message>기관에 확인</message></item>"))

        with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "test-key+/="}):
            service = PublicDataService(transport=httpx.MockTransport(respond))
            hospitals = await service.hospitals("청도")
            specialties = await service.hospital_specialties(hospitals["items"][0]["id"])
            vaccines = await service.vaccines()
            details = await service.vaccine_detail(vaccines["items"][0]["code"])
        self.assertEqual(requests[0].url.params["ServiceKey"], "test-key+/=")
        self.assertEqual(requests[0].url.params["yadmNm"], "청도")
        self.assertEqual(requests[1].url.params["serviceKey"], "test-key+/=")
        self.assertEqual(requests[1].url.params["ykiho"], "abc+/=")
        self.assertEqual(specialties["items"][0]["name"], "내과")
        self.assertEqual(vaccines["items"][0]["code"], "01")
        self.assertEqual(details["items"][0]["message"], "기관에 확인")
        self.assertTrue(all(result["retrieved_at"] and result["source"]["url"]
                            for result in (hospitals, specialties, vaccines, details)))

    async def test_missing_key_and_invalid_or_failed_responses(self):
        with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "", "PUBLIC_DECODING_KEY": ""}):
            with self.assertRaises(PublicDataUnavailable):
                await PublicDataService().vaccines()
        for status, body in (
            (401, "denied"), (200, xml("", code="99")), (200, "<invalid"),
            (200, '<!DOCTYPE x [<!ENTITY x "x">]><response/>'),
            (200, "x" * (1024 * 1024 + 1)),
        ):
            with self.subTest(status=status, body=body[:20]):
                transport = httpx.MockTransport(lambda _request: httpx.Response(status, text=body))
                with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "test-key"}):
                    with self.assertRaises(PublicDataError):
                        await PublicDataService(transport=transport).vaccines()
