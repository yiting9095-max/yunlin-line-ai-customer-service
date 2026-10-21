import os
import hmac
import hashlib
import base64
import json
import uuid
import html
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import requests
import gspread
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from google.oauth2.service_account import Credentials
from openai import OpenAI

app = FastAPI(title="耘箖環衛 LINE AI 客服")
security = HTTPBasic()

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

TAIPEI = ZoneInfo("Asia/Taipei")


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """以 Render 環境變數驗證管理員；未設定帳密時拒絕管理操作。"""
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="管理員帳號尚未設定，請在 Render 設定 ADMIN_USERNAME 與 ADMIN_PASSWORD。",
        )
    username_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        ADMIN_USERNAME.encode("utf-8"),
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        ADMIN_PASSWORD.encode("utf-8"),
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="管理員帳號或密碼錯誤",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


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
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)


def get_cases_sheet():
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    return spreadsheet.worksheet("客服案件紀錄")


def get_line_display_name(user_id):
    """查詢 LINE 顯示名稱；失敗時回傳空字串。"""
    if not user_id or user_id == "無法取得使用者ID":
        return ""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("LINE 暱稱查詢失敗：未設定 Access Token")
        return ""
    try:
        response = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=8,
        )
        if response.status_code == 200:
            return response.json().get("displayName", "").strip()
        print(f"LINE 暱稱查詢未成功，HTTP 狀態碼：{response.status_code}")
    except Exception as e:
