import os
import requests
from fastapi import FastAPI, Request, Header, HTTPException
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = FastAPI()

# ================= CONFIG =================
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("LINE env not set")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)

API_BASE = "https://inventory-api-659i.onrender.com"

DEFAULT_BRANCH_ID = 1   # ⭐ สาขาที่ LINE ใช้
LOW_STOCK = 5

# ================= HELPERS =================
def fetch_products():
    try:
        res = requests.get(
            f"{API_BASE}/products/",
            params={"branch_id": DEFAULT_BRANCH_ID},
            timeout=10,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise RuntimeError(str(e))


def all_in_stock(products):
    return [p for p in products if (p.get("quantity") or 0) > LOW_STOCK]


def low_in_stock(products):
    return [
        p for p in products
        if 0 < (p.get("quantity") or 0) <= LOW_STOCK
    ]


def out_of_stock(products):
    return [p for p in products if (p.get("quantity") or 0) == 0]


def format_product(p):
    return (
        f"📦 {p.get('name')}\n"
        f"฿{p.get('price')} • Qty: {p.get('quantity')}"
    )


# ================= WEBHOOK =================
@app.post("/line/webhook")
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
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessage):
            continue

        text = event.message.text.strip().lower()

        # ---------- TEST ----------
        if text == "ping":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="pong ✅ inventory connected"),
            )
            continue

        # ---------- LOGIN ----------
        if text in ("login", "register"):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "🔐 Pepino Inventory\n\n"
                        "Login / Register 👇\n"
                        "https://inventory-web-14d4.onrender.com"
                    )
                ),
            )
            continue

        # ---------- FETCH ----------
        try:
            products = fetch_products()
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ API error\n{e}"),
            )
            continue

        # ---------- COMMANDS ----------
        if text == "all in stock":
            items = all_in_stock(products)
            title = "📦 All in Stock"

        elif text == "low in stock":
            items = low_in_stock(products)
            title = "⚠️ Low in Stock"

        elif text == "out of stock":
            items = out_of_stock(products)
            title = "⛔ Out of Stock"

        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "❓ คำสั่งที่ใช้ได้\n\n"
                        "• all in stock\n"
                        "• low in stock\n"
                        "• out of stock"
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
