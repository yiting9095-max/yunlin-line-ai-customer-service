
import os
import hmac
import hashlib
import base64
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from google.oauth2.service_account import Credentials

app = FastAPI(title="耘箖環衛 LINE AI 客服")

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
)


def get_google_sheets_client():
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("尚未設定 Google 服務帳戶金鑰")

    if not GOOGLE_SHEET_ID:
        raise RuntimeError("尚未設定 Google 試算表 ID")

    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        info, scopes=scopes
    )

    return gspread.authorize(credentials)


def get_cases_sheet():
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    return spreadsheet.worksheet("客服案件紀錄")


def save_customer_message(user_id, message):
    sheet = get_cases_sheet()

    now = datetime.now(ZoneInfo("Asia/Taipei"))
    case_id = "YL-" + now.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()

    row = [
        case_id,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        user_id or "無法取得使用者ID",
        message,
        "",
        "待審核",
        "",
        "未發送",
        "",
        "",
    ]

    sheet.append_row(row, value_input_option="USER_ENTERED")


@app.get("/")
async def health_check():
    return {
        "service": "耘箖環衛 LINE AI 客服",
        "status": "running"
    }


@app.get("/test-sheets")
async def test_sheets():
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        return {
            "status": "connected",
            "spreadsheet": spreadsheet.title,
            "worksheets": [
                worksheet.title
                for worksheet in spreadsheet.worksheets()
            ],
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Google 試算表連線失敗"
        )


@app.post("/webhook")
async def line_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("x-line-signature", "")

    if not CHANNEL_SECRET:
        raise HTTPException(
            status_code=500,
            detail="LINE_CHANNEL_SECRET 尚未設定"
        )

    digest = hmac.new(
        CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()

    expected_signature = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(
            status_code=400,
            detail="Invalid signature"
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        # 目前只記錄文字訊息，不處理圖片、貼圖或檔案。
        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()
        if not text:
            continue

        source = event.get("source", {})
        user_id = source.get("userId", "")

        try:
            save_customer_message(user_id, text)
        except Exception:
            # 回傳失敗讓 LINE 有機會重試，不記錄敏感內容到日誌。
            raise HTTPException(
                status_code=500,
                detail="案件寫入失敗"
            )

    # 不呼叫 AI、不使用 reply token、不自動傳送 LINE 訊息。
    return JSONResponse({"status": "ok"})
