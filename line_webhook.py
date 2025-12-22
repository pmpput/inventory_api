# line_webhook.py
import os
import requests
from fastapi import APIRouter, Request, Header, HTTPException
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

router = APIRouter()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)
API_BASE = "https://inventory-api-659i.onrender.com"

LOW_STOCK_THRESHOLD = 5  # ต้องตรงกับ home_page.dart

def fetch_all_in_stock():
    res = requests.get(f"{API_BASE}/products/")
    res.raise_for_status()
    products = res.json()

    return [
        p for p in products
        if (p.get("quantity") or 0) > LOW_STOCK_THRESHOLD
    ]

def fetch_low_stock():
    res = requests.get(f"{API_BASE}/products/")
    res.raise_for_status()
    products = res.json()

    return [
        p for p in products
        if 0 < (p.get("quantity") or 0) <= LOW_STOCK_THRESHOLD
    ]

def fetch_out_of_stock():
    res = requests.get(f"{API_BASE}/products/")
    res.raise_for_status()
    products = res.json()

    return [
        p for p in products
        if (p.get("quantity") or 0) == 0
    ]

def format_product_text(p):
    return (
        f"{p.get('name')}\n"
        f"฿{p.get('price')} • Qty: {p.get('quantity')}\n"
        f"Unit: {p.get('unit') or 'None'} • "
        f"Category: {p.get('category') or '-'}"
    )


@router.post("/line/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(None),
):
    body = await request.body()
    try:
        events = parser.parse(body.decode("utf-8"), x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            text = event.message.text.strip().lower()

            # test command
            if text == "ping":
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="pong ✅ Inventory system connected")
                )

            if text == "login" or text == "register":
               line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
            text=(
                "🔐 เข้าสู่ระบบ Pepino Inventory\n\n"
                "คลิกที่ลิงก์ด้านล่างเพื่อ Login / Register 👇\n"
                "https://inventory-web-14d4.onrender.com"
            )
        )
    )    

             # ---------- ALL IN STOCK ----------
            elif text == "All in Stock":
                products = fetch_all_in_stock()

                if not products:
                    reply = "📦 All in Stock\nไม่มีสินค้าที่อยู่ในสต็อก"
                else:
                    reply = "📦 All in Stock\n\n" + "\n\n".join(
                        format_product_text(p) for p in products
                    )

                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply)
                )

            # ---------- LOW IN STOCK ----------
            elif text == "Low in Stock":
                products = fetch_low_stock()

                if not products:
                    reply = "⚠️ Low in Stock\nไม่มีสินค้าที่ใกล้หมด"
                else:
                    reply = "⚠️ Low in Stock\n\n" + "\n\n".join(
                        format_product_text(p) for p in products
                    )

                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply)
                )

            # ---------- OUT OF STOCK ----------
            elif text == "Out of Stock":
                products = fetch_out_of_stock()

                if not products:
                    reply = "⛔ Out of Stock\nไม่มีสินค้าที่หมด"
                else:
                    reply = "⛔ Out of Stock\n\n" + "\n\n".join(
                        format_product_text(p) for p in products
                    )

                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply)
                )    

    return {"status": "ok"}
