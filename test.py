# Python 3.10

import http.client
import ssl
import json
import asyncio  ##고루틴, 채널 개념의 병렬 처리 기능 라이브러리
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from datetime import datetime, timedelta, timezone
import aiohttp




def get_token() -> str:   ## askurl console 작업에 필요한 로그인 토큰을 획득(토큰 유효기간 1시간)
    host = "console.askurl.io"
    path = "/api/v1/users/auth"

    payload = '{"platform":"nurilab","authCode":"","email":"asdfasdfasdfasdf","password":"asdfasdfasdfasdf"}'
    body_bytes = payload.encode("utf-8")
    content_length = str(len(body_bytes))

    headers = [
        ("Host", "console.askurl.io"),
        ("Connection", "keep-alive"),
        ("Content-Length", content_length),
        ('sec-ch-ua-platform', '"Windows"'),
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"),
        ("Accept", "application/json, text/plain, */*"),
        ('sec-ch-ua', '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"'),
        ("Content-Type", "application/json"),
        ("sec-ch-ua-mobile", "?0"),
        ("Origin", "https://console.askurl.io"),
        ("Sec-Fetch-Site", "same-origin"),
        ("Sec-Fetch-Mode", "cors"),
        ("Sec-Fetch-Dest", "empty"),
        ("Referer", "https://console.askurl.io/login"),
        ("Accept-Encoding", "identity"),  # 비압축 본문 강제
        ("Accept-Language", "ko-KR,ko;q=0.9"),
        ("Cookie", "_clck=1edlvcj%7C2%7Cfyg%7C0%7C2052; _ga=GA1.1.1777455270.1755133023; _clsk=1d20mqe%7C1755133109543%7C3%7C1%7Cv.clarity.ms%2Fcollect; _ga_50HPCTFVRW=GS2.1.s1755133023$o1$g1$t1755133117$j51$l0$h0"),
    ]

    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, 443, context=context)

    try:
        conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        for k, v in headers:
            conn.putheader(k, v)
        conn.endheaders(body_bytes)

        resp = conn.getresponse()
        status = resp.status
        reason = resp.reason
        resp_body = resp.read()
    finally:
        conn.close()

    if status != 200:
        raise RuntimeError(f"HTTP {status}: {reason}")

    try:
        data = json.loads(resp_body.decode("utf-8"))
    except Exception as e:
        raise ValueError("응답 JSON 파싱에 실패했다.") from e

    if "access_jwt" not in data:
        raise KeyError("응답에 access_jwt 필드가 없다.")

    return data["access_jwt"]





def _build_range_ms_kst_for_yesterday() -> tuple[int, int]:
    kst = timezone(timedelta(hours=9))  # 고정 UTC+9
    now = datetime.now(kst)
    y = (now - timedelta(days=1)).date()
    start = datetime(y.year, y.month, y.day, tzinfo=kst)  # 어제 00:00:00 KST
    end = start + timedelta(days=1)                       # 오늘 00:00:00 KST
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

def _make_payload(page: int, start_ms: int, end_ms: int, limit: int = 100) -> bytes:
    prev = page - 1 if page > 1 else 0
    data = {
        "total": -1,
        "limit": limit,
        "prev": prev,
        "page": page,
        "sort": [{"key": "created_at", "value": -1}],
        "filter": {"$or": [{"created_at": {"$gte": start_ms, "$lt": end_ms, "$ne": 0}}]},
    }
    return json.dumps(data, separators=(",", ":")).encode("utf-8")

def _post_search(console_token: str, body_bytes: bytes, referer_page: int) -> str:
    host = "console.askurl.io"
    path = "/api/v1/requests/search"
    content_length = str(len(body_bytes))

    headers = [
        ("Host", host),
        ("Connection", "keep-alive"),
        ("Content-Length", content_length),
        ("X-ACCESS-TOKEN", console_token),
        ('sec-ch-ua-platform', '"Windows"'),
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"),
        ("Accept", "application/json, text/plain, */*"),
        ('sec-ch-ua', '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"'),
        ("Content-Type", "application/json"),
        ("sec-ch-ua-mobile", "?0"),
        ("Origin", "https://console.askurl.io"),
        ("Sec-Fetch-Site", "same-origin"),
        ("Sec-Fetch-Mode", "cors"),
        ("Sec-Fetch-Dest", "empty"),
        ("Referer", f"https://console.askurl.io/scanrequest/url?page={referer_page}"),
        ("Accept-Encoding", "identity"),
        ("Accept-Language", "ko-KR,ko;q=0.9"),
    ]

    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, 443, context=context)
    try:
        conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        for k, v in headers:
            conn.putheader(k, v)
        conn.endheaders(body_bytes)
        resp = conn.getresponse()
        resp_body = resp.read()  # chunked 자동 처리
        return resp_body.decode("utf-8", errors="replace")
    finally:
        conn.close()



def write_rows_if_new_by_url_id(data):
    """
    'rows'의 각 객체를 url_id 기준으로 중복 확인 후,
    현재 파이썬 파일과 동일한 디렉토리의 'request_result.txt'에
    NDJSON(한 줄에 한 객체) 형태로 기록한다.
    파일이 없으면 생성한다.
    인자는 data 한 개만 받는다.
    반환값은 처리 통계 dict이다.
    """
    # 파일 경로 결정 및 파일 존재 보장
    try:
        base_dir = Path(__file__).resolve().parent
    except NameError:
        base_dir = Path.cwd()
    file_path = base_dir / "request_result.txt"
    file_path.touch(exist_ok=True)

    # data 정규화: JSON 문자열/bytes -> dict
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise TypeError("data는 dict 또는 JSON 문자열이어야 합니다.")

    rows = data.get("rows")
    if not isinstance(rows, list):
        raise ValueError("'rows' 키가 없거나 리스트가 아닙니다.")

    # 기존 url_id 집합 로드
    existing_ids = set()
    with file_path.open("r", encoding="utf-8") as rf:
        for line in rf:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            uid = obj.get("url_id")
            if isinstance(uid, str):
                existing_ids.add(uid)

    # 신규만 기록
    inserted = 0
    skipped = 0
    with file_path.open("a", encoding="utf-8") as wf:
        for obj in rows:
            if not isinstance(obj, dict):
                skipped += 1
                continue
            # 여기 추가: status가 4가 아니면 무조건 스킵
            if obj.get("status") != 4:
                skipped += 1
                continue
            uid = obj.get("url_id")
            if not isinstance(uid, str) or uid in existing_ids:
                skipped += 1
                continue
            wf.write(json.dumps(obj, ensure_ascii=False) + "\n")
            existing_ids.add(uid)
            inserted += 1

    return {"inserted": inserted, "skipped": skipped, "total_processed": len(rows), "file": str(file_path)}


async def _fetch_and_forward(page: int, console_token: str, start_ms: int, end_ms: int):
    payload = _make_payload(page, start_ms, end_ms, limit=100)
    result = await asyncio.to_thread(_post_search, console_token, payload, page)
    await asyncio.to_thread(write_rows_if_new_by_url_id, result)

async def request_search(console_token: str) -> None:
    start_ms, end_ms = _build_range_ms_kst_for_yesterday()
    tasks = [_fetch_and_forward(p, console_token, start_ms, end_ms) for p in range(1, 11)]
    await asyncio.gather(*tasks)


async def check_FR(session: aiohttp.ClientSession, data: dict) -> None:
    url_id = data.get("url_id")
    if not url_id:
        return
    url = f"https://console.askurl.io/api/v1/scanresults/{url_id}/summary"
    headers = {
        "X-ACCESS-TOKEN": console_token,
        "X-APIKEY": "db79c45b-1a60-4afc-9410-f2f0e2b0247a",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "identity",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }
    async with session.get(url, headers=headers) as resp:
        resp.raise_for_status()
        text = await resp.text()
        print(text)


async def process_saved_results() -> None:
    file_path = Path(__file__).resolve().parent / "request_result.txt"
    if not file_path.exists():
        return

    rows: list[dict] = []
    with file_path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    async with aiohttp.ClientSession() as session:
        tasks = [check_FR(session, row) for row in rows]
        await asyncio.gather(*tasks)









console_token = get_token()  ##전역변수 console_token에 토큰 획득해서 저장


async def main() -> None:
    await request_search(console_token)
    await process_saved_results()


asyncio.run(main())




