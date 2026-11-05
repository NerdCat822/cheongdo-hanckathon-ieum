import os
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx


class PublicDataUnavailable(Exception):
    pass


class PublicDataError(Exception):
    pass


HOSPITAL_SOURCE = {
    "title": "건강보험심사평가원 병원정보서비스",
    "url": "https://www.data.go.kr/data/15001698/openapi.do",
}
DETAIL_SOURCE = {
    "title": "건강보험심사평가원 의료기관별상세정보서비스",
    "url": "https://www.data.go.kr/data/15001699/openapi.do",
}
VACCINE_SOURCE = {
    "title": "질병관리청 예방접종 대상 감염병 정보",
    "url": "https://www.data.go.kr/data/15084296/openapi.do",
}
FACILITY_SOURCE = {
    "title": "국토교통부 노인복지시설",
    "url": "https://www.data.go.kr/data/15056929/openapi.do",
}


class PublicDataService:
    def __init__(self, transport=None):
        self.key = os.getenv("DATA_GO_KR_SERVICE_KEY") or os.getenv("PUBLIC_DECODING_KEY", "")
        self.transport = transport

    async def _get_xml(self, url, params, key_name):
        if not self.key:
            raise PublicDataUnavailable()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0), transport=self.transport, follow_redirects=False, trust_env=False
            ) as client:
                async with client.stream("GET", url, params={**params, key_name: self.key}) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 1024 * 1024:
                            raise PublicDataError()
        except httpx.HTTPError as exc:
            raise PublicDataError() from exc
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise PublicDataError()
        try:
            root = ElementTree.fromstring(data)
        except ElementTree.ParseError as exc:
            raise PublicDataError() from exc
        code = root.findtext(".//resultCode")
        if code not in {"00", "0000", "0"}:
            raise PublicDataError()
        return root

    @staticmethod
    def _response(source, data):
        return {"source": source, "retrieved_at": datetime.now(timezone.utc).isoformat(), "items": data}

    async def hospitals(self, name):
        root = await self._get_xml(
            "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList",
            {"pageNo": 1, "numOfRows": 10, "yadmNm": name}, "ServiceKey",
        )
        items = [{
            "id": item.findtext("ykiho", ""),
            "name": item.findtext("yadmNm", ""),
            "address": item.findtext("addr", ""),
            "phone": item.findtext("telno", ""),
            "type": item.findtext("clCdNm", ""),
        } for item in root.findall(".//items/item")]
        return self._response(HOSPITAL_SOURCE, items)

    async def hospital_specialties(self, hospital_id):
        root = await self._get_xml(
            "https://apis.data.go.kr/B551182/MadmDtlInfoService2.8/getDgsbjtInfo2.8",
            {"pageNo": 1, "numOfRows": 100, "ykiho": hospital_id, "_type": "xml"}, "serviceKey",
        )
        items = [{
            "name": item.findtext("dgsbjtCdNm", ""),
            "specialists": item.findtext("dgsbjtPrSdrCnt", ""),
        } for item in root.findall(".//items/item")]
        return self._response(DETAIL_SOURCE, items)

    async def vaccines(self):
        root = await self._get_xml(
            "https://apis.data.go.kr/1790387/vcninfo/getCondVcnCd", {}, "ServiceKey",
        )
        items = [{"code": item.findtext("cd", ""), "name": item.findtext("cdNm", "")}
                 for item in root.findall(".//items/item")]
        return self._response(VACCINE_SOURCE, items)

    async def vaccine_detail(self, code):
        root = await self._get_xml(
            "https://apis.data.go.kr/1790387/vcninfo/getVcnInfo", {"vcnCd": code}, "ServiceKey",
        )
        items = [{"title": item.findtext("title", ""), "message": item.findtext("message", "")}
                 for item in root.findall(".//items/item")]
        return self._response(VACCINE_SOURCE, items)
