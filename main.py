
import os
import hmac
import hashlib
import base64
import json

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
        raise RuntimeError(
            "尚未設定 GOOGLE_SERVICE_ACCOUNT_JSON"
        )

    if not GOOGLE_SHEET_ID:
        raise RuntimeError(
            "尚未設定 GOOGLE_SHEET_ID"
        )

    service_account_info = json.loads(
        GOOGLE_SERVICE_ACCOUNT_JSON
    )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes,
    )

    return gspread.authorize(credentials)


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

        worksheets = [
            worksheet.title
            for worksheet in spreadsheet.worksheets()
        ]

        return {
            "status": "connected",
            "spreadsheet": spreadsheet.title,
            "worksheets": worksheets,
        }

    except Exception:
        # 不回傳金鑰或完整錯誤內容，避免洩漏機密。
        raise HTTPException(
            status_code=500,
            detail="Google 試算表連線失敗，請檢查 Render Logs"
        )


@app.post("/webhook")
async def line_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get(
        "x-line-signature", ""
    )

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

    expected_signature = base64.b64encode(
        digest
    ).decode("utf-8")

    if not hmac.compare_digest(
        expected_signature, signature
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid signature"
        )

    # 目前只驗證 LINE Webhook，不讀取或儲存客戶訊息，
    # 不呼叫 AI，也不自動傳送 LINE 回覆。
    return JSONResponse({"status": "ok"})
