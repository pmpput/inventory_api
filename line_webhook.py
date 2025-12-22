# line_products.py
import os
import requests
from fastapi import APIRouter, Request, Header, HTTPException
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

router = APIRouter()

# ---------------- CONFIG ----------------
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

API_BASE = "https://inventory-api-659i.onrender.com"
LOW_STOCK_THRESHOLD = 5  # ต้องตรงกับ Flutter

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)

# เก็บ branch ของ user (prototype)
USER_BRANCH = {}  # key = line userId, value = branchId

# ---------------- API HELPERS ----------------
def fetch_products(branch_id: int):
    res = requests.get(
        f"{API_BASE}/products/",
        params={"branch_id": branch_id},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def fetch_all_in_stock(branch_id: int):
    products = fetch_products(branch_id)
    return [
        p for p in products
        if (p.get("quantity") or 0) > LOW_STOCK_THRESHOLD
    ]


def fetch_low_stock(branch_id: int):
    products = fetch_products(branch_id)
    return [
        p for p in products
        if 0 < (p.get("quantity") or 0) <= LOW_STOCK_THRESHOLD
    ]


def fetch_out_of_stock(branch_id: int):
    products = fetch_products(branch_id)
    return [
        p for p in products
        if (p.get("quantity") or 0) == 0
    ]


def format_product_text(p: dict) -> str:
    return (
        f"{p.get('name')}\n"
        f"฿{p.get('price')} • Qty: {p.get('quantity')}\n"
        f"Unit: {p.get('unit') or 'None'} • "
        f"Category: {p.get('category') or '-'}"
    )

# ---------------- WEBHOOK ----------------
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
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessage):
            continue

        text = event.message.text.strip().lower()
        user_id = event.source.user_id

        # ---------- PING ----------
        if text == "ping":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="pong ✅ Inventory system connected")
            )
            continue

        # ---------- LOGIN ----------
        if text in ("login", "register"):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "🔐 เข้าสู่ระบบ Pepino Inventory\n\n"
                        "คลิกที่ลิงก์ด้านล่าง 👇\n"
                        "https://inventory-web-14d4.onrender.com"
                    )
                )
            )
            continue

        # ---------- SELECT BRANCH ----------
        if text.startswith("branch"):
            try:
                # branch 1
                branch_id = int(text.split(" ")[1])
                USER_BRANCH[user_id] = branch_id

                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=f"✅ ตั้งค่าสาขาเป็น Branch {branch_id} แล้ว"
                    )
                )
            except Exception:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text="❌ รูปแบบไม่ถูกต้อง\nตัวอย่าง: branch 1"
                    )
                )
            continue

        # ---------- CHECK BRANCH ----------
        branch_id = USER_BRANCH.get(user_id)
        if not branch_id:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="❗ กรุณาเลือกสาขาก่อน\nพิมพ์: branch 1"
                )
            )
            continue

        # ---------- ALL IN STOCK ----------
        if text == "all in stock":
            products = fetch_all_in_stock(branch_id)
            title = f"📦 All in Stock (Branch {branch_id})"

        # ---------- LOW IN STOCK ----------
        elif text == "low in stock":
            products = fetch_low_stock(branch_id)
            title = f"⚠️ Low in Stock (Branch {branch_id})"

        # ---------- OUT OF STOCK ----------
        elif text == "out of stock":
            products = fetch_out_of_stock(branch_id)
            title = f"⛔ Out of Stock (Branch {branch_id})"

        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "❓ คำสั่งที่ใช้ได้\n\n"
                        "branch 1\n"
                        "all in stock\n"
                        "low in stock\n"
                        "out of stock"
                    )
                )
            )
            continue

        # ---------- REPLY PRODUCT LIST ----------
        if not products:
            reply = f"{title}\n\nไม่มีสินค้า"
        else:
            reply = title + "\n\n" + "\n\n".join(
                format_product_text(p) for p in products
            )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

    return {"status": "ok"}
