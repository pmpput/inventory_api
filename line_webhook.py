import os
import httpx
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
DEFAULT_BRANCH_ID = 1

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("LINE credentials not set")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)

# ================== HELPERS ==================
async def fetch_products(branch_id: int):
    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(
            f"{API_BASE}/line/products",
            params={"branch_id": branch_id},
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

def parse_product_form(text: str) -> dict:
    
    product = {}

    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key in ("price", "quantity", "branch_id"):
            product[key] = int(value)
        else:
            product[key] = value

    return product


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
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessage):
            continue

        raw_text = event.message.text.strip()
        text = raw_text.lower()

        # ---------- PING ----------
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

        # ---------- SHOW ADD PRODUCT FORM ----------
        if text in ("add product", "add product line"):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=(
                        "📝 เพิ่มสินค้า (กรอกให้ครบ แล้วส่งกลับ)\n\n"
                        "name: \n"
                        "price: \n"
                        "quantity: \n"
                        "unit: \n"
                        "category: \n"
                        "branch_id: 1"
                    )
                ),
            )
            continue

        # ---------- SUBMIT PRODUCT FORM ----------
        if "name:" in text and "price:" in text and "quantity:" in text:
            try:
                product = parse_product_form(raw_text)

                required = ["name", "price", "quantity", "branch_id"]
                for r in required:
                    if r not in product:
                        raise ValueError(f"missing field: {r}")

                # ✅ ตอบ LINE ก่อน (สำคัญที่สุด)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=(
                            "⏳ กำลังเพิ่มสินค้า...\n\n"
                            f"📦 {product['name']}\n"
                            f"Qty: {product['quantity']}"
                        )
                    ),
                )

                # ✅ ค่อยยิง API ทีหลัง 
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{API_BASE}/line/add-product",
                        json=product,
                    )

            except Exception as e:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"❌ เพิ่มสินค้าไม่สำเร็จ\n{e}"),
                )
            continue

        # ---------- FETCH PRODUCTS ----------
        try:
            products = await fetch_products(DEFAULT_BRANCH_ID)
        except Exception:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="❌ ไม่สามารถเชื่อมต่อระบบคลังสินค้าได้ กรุณาลองใหม่อีกครั้ง"
                ),
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
                        "❓ คำสั่งไม่ถูกต้อง\n\n"
                        "พิมพ์ได้:\n"
                        "- all in stock\n"
                        "- low in stock\n"
                        "- out of stock\n"
                        "- add product"
                    )
                ),
            )
            continue

        # ---------- RESPONSE ----------
        if not items:
            reply = f"{title}\nไม่มีสินค้า"
        else:
            reply = f"{title}\n\n" + "\n\n".join(
                format_product(p) for p in items[:10]
            )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply),
        )

    return {"status": "ok"}
