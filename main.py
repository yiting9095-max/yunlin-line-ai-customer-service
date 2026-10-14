import os
import hmac
import hashlib
import base64

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="耘箖環衛 LINE AI 客服")

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")


@app.get("/")
async def health_check():
    return {
        "service": "耘箖環衛 LINE AI 客服",
        "status": "running"
    }


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

    # 第一階段：只接收並驗證 LINE Webhook。
    # 不呼叫 AI、不發送任何 LINE 回覆。
    return JSONResponse({"status": "ok"})
