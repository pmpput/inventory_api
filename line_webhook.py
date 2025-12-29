# line_products.py
import os
import requests
from fastapi import APIRouter, Request, Header, HTTPException
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
)

router = APIRouter()

# ================== CONFIG ==================
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

API_BASE = "https://inventory-api-659i.onrender.com"
LOW_STOCK_THRESHOLD = 5

DEFAULT_BRANCH_ID = 1  # ⭐ ปรับเป็น branch ที่ต้องการ

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("LINE credentials not set")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)

# ================== HELPERS ==================
def fetch_products(branch_id: int):
    res = requests.get(
        f"{API_BASE}/line/products",
        params={"branch_id": branch_id},
        timeout=20,
    )
    res.raise_for_status()
    return res.json()


def all_in_stock(products):
    return [p for p in products if (p.get("quantity") or 0) > LOW_STOCK_THRESHOLD]


def low_in_stock(products):
    return [
        p for p in products
        if 0 < (p.get("quantity") or 0) <= LOW_STOCK_THRESHOLD
    ]


def out_of_stock(products):
    return [p for p in products if (p.get("quantity") or 0) == 0]


def format_product(p):
    return (
        f"📦 {p.get('name')}\n"
        f"฿{p.get('price')} • Qty: {p.get('quantity')}\n"
        f"Unit: {p.get('unit') or '-'} • "
        f"Category: {p.get('category') or '-'}"
    )


# ================== WEBHOOK ==================
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
        if not (
            isinstance(event, MessageEvent)
            and isinstance(event.message, TextMessage)
        ):
            continue

        text = event.message.text.strip().lower()

        # ---------- TEST ----------
        if text == "ping":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="pong ✅ Inventory system connected"),
            )
            continue

        # ---------- LOGIN ----------
        if text in ("login", "register"):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "🔐 Pepino Inventory System\n\n"
                        "Login / Register ได้ที่ 👇\n"
                        "https://inventory-web-14d4.onrender.com"
                    )
                ),
            )
            continue

        # ---------- FETCH PRODUCTS ----------
        try:
            products = fetch_products(DEFAULT_BRANCH_ID)
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ API Error: {e}"),
            )
            continue

        # ---------- ALL IN STOCK ----------
        if text == "all in stock":
            items = all_in_stock(products)
            title = "📦 All in Stock"

        # ---------- LOW IN STOCK ----------
        elif text == "low in stock":
            items = low_in_stock(products)
            title = "⚠️ Low in Stock"

        # ---------- OUT OF STOCK ----------
        elif text == "out of stock":
            items = out_of_stock(products)
            title = "⛔ Out of Stock"

        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "❓ คำสั่งไม่ถูกต้อง\n\n"
                        "พิมพ์ได้เฉพาะ:\n"
                        "- all in stock\n"
                        "- low in stock\n"
                        "- out of stock"
                    )
                ),
            )
            continue

        # ---------- RESPONSE ----------
        if not items:
            reply = f"{title}\nไม่มีสินค้า"
        else:
            reply = f"{title}\n\n" + "\n\n".join(
                format_product(p) for p in items
            )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply),
        )

    return {"status": "ok"}
