"""국민연금공단 가입 사업장 내역 (공공데이터포털). 공시가 없는 회사의 직원 수를 본다."""

import re
import xml.etree.ElementTree as ET

import httpx

from career_ai.http import get

API = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2"
ACTIVE = "1"  # wkplJnngStcd: 1 가입, 2 탈퇴


class NpsError(Exception):
    """공공데이터포털이 오류를 돌려줬을 때."""


def _items(xml: bytes) -> list[ET.Element]:
    root = ET.fromstring(xml)
    code = root.findtext("header/resultCode")
    if code != "00":
        # 인증키 오류 등은 <OpenAPI_ServiceResponse>로 온다.
        message = root.findtext("header/resultMsg") or root.findtext(
            "cmmMsgHeader/returnAuthMsg")
        raise NpsError(f"국민연금 사업장 조회 오류: {message}")
    return root.findall(".//item")


def _normalize(name: str) -> str:
    return re.sub(r"\(주\)|㈜|주식회사|\s", "", name)


def parse_workplaces(xml: bytes) -> list[dict]:
    return [
        {
            "seq": item.findtext("seq"),
            "name": item.findtext("wkplNm"),
            "address": item.findtext("wkplRoadNmDtlAddr"),
            "active": item.findtext("wkplJnngStcd") == ACTIVE,
            "data_month": item.findtext("dataCrtYm"),
        }
        for item in _items(xml)
    ]


def find(workplaces: list[dict], name: str) -> list[dict]:
    """이름이 같고 가입 중인 사업장."""
    query = _normalize(name)
    return [w for w in workplaces if w["active"] and _normalize(w["name"]) == query]


def search(client: httpx.Client, key: str, name: str, *, backoff: float = 1.0) -> list[dict]:
    params = {"serviceKey": key, "wkpl_nm": name, "pageNo": 1, "numOfRows": 100}
    response = get(client, f"{API}/getBassInfoSearchV2", params=params, backoff=backoff)
    return parse_workplaces(response.content)


def detail(client: httpx.Client, key: str, seq: str, *, backoff: float = 1.0) -> dict:
    response = get(client, f"{API}/getDetailInfoSearchV2",
                   params={"serviceKey": key, "seq": seq}, backoff=backoff)
    [item] = _items(response.content)
    adopted = item.findtext("adptDt") or ""
    return {
        "employees": int(item.findtext("jnngpCnt") or 0) or None,
        "adopted": f"{adopted[:4]}-{adopted[4:6]}-{adopted[6:8]}" if len(adopted) == 8 else None,
        "industry": item.findtext("vldtVlKrnNm"),
    }
