# import sys
# import asyncio
# import os
# import json
# import re
# import pandas as pd
# import uvicorn
# import nest_asyncio
# from typing import List, Dict

# from fastapi import FastAPI, Request, HTTPException, Header
# from pydantic import BaseModel

# # LINE SDK
# # from linebot import LineBotApi, WebhookHandler
# # from linebot.exceptions import InvalidSignatureError
# # from linebot.models import (
# #     MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
# #     BubbleContainer, BoxComponent, TextComponent, SeparatorComponent
# # )

# # 1. Allow nested event loops
# nest_asyncio.apply()

# if sys.platform == "win32":
#     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# # IMPORT YOUR SCRAPERS
# from retailer_scraper import scrape_search, find_best_deals
# from ai_matcher import SmartMatcher

# # ==========================================
# # 🔧 CONFIG
# # ==========================================
# # REPLACE WITH YOUR KEYS
# # LINE_CHANNEL_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE" 
# # LINE_CHANNEL_SECRET = "YOUR_CHANNEL_SECRET_HERE"

# # line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
# # handler = WebhookHandler(LINE_CHANNEL_SECRET)

# CACHE = {"engine": None}

# TARGETS = [
#     {
#         "name": "BigC",
#         "search_url": "https://www.bigc.co.th/en/search?q={q}",
#         "selectors": {"product_card": 'div.productItem, div[data-testid="product-card"]', "name": ".product-name", "price": ".product-price"},
#     },
#     {
#         "name": "Tops",
#         "search_url": "https://www.tops.co.th/en/search/{q}",
#         "selectors": {"product_card": ".product-item-info", "name": ".product-item-link", "price": ".price"},
#     },
#     {
#         "name": "Makro",
#         "search_url": "https://www.makro.pro/en/c/search?q={q}",
#         "selectors": {"product_card": 'div[class*="product-card"]', "name": 'span[class*="name"]', "price": 'span[class*="price"]'},
#     },
# ]

# app = FastAPI()

# class CompareRequest(BaseModel):
#     items: List[str]

# # ==========================================
# # 🧠 CORE LOGIC
# # ==========================================
# def _norm(s: str) -> str:
#     return re.sub(r"\s+", " ", (s or "").strip().lower())

# def clean_search_results(query: str, results: List[dict]) -> List[dict]:
#     q = _norm(query)

#     PET_WORDS = ["nekko", "me-o", "meo", "whiskas", "friskies", "purina", "kaniva", "cat", "kitten", "dog", "puppy", "pet", "cesar", "pedigree", "smartheart", "royal canin", "jerhigh", "tito", "bok dok", "monchou", "อาหารแมว", "อาหารสุนัข", "แมว", "สุนัข", "pouch", "jelly", "gravy", "topping", "litter", "sand"]
    
#     NON_FOOD_WORDS = ["ตุ๊กตา", "ของเล่น", "พวงกุญแจ", "หมอน", "เสื้อ", "กระเป๋า", "ผ้า", "รองเท้า", "ของใช้", "ของตกแต่ง", "toy", "doll", "plush", "stuffed", "keychain", "shirt", "bag", "decor", "mouthwash", "toothpaste", "dental", "น้ำยาบ้วนปาก", "ยาสีฟัน", "แปรงสีฟัน", "shampoo", "soap", "แชมพู", "สบู่", "listerine", "colgate"]
    
#     COOKED_WORDS = ["ทอด", "ย่าง", "อบ", "ต้ม", "นึ่ง", "ปรุงสุก", "พร้อมทาน", "สำเร็จรูป", "ready", "cooked", "fried", "roasted", "bbq", "grilled", "meal", "set", "box", "retort"]
    
#     # ✅ Baby Food Block List
#     BABY_FOOD_WORDS = ["baby", "puree", "peachy", "cerelac", "hooray", "picnic", "kiddy", "kid", "toddler", "infant", "อาหารเด็ก", "อาหารทารก", "บดละเอียด", "pouch"]

#     # ✅ Added Porridge/Soup/Broth
#     PROCESSED_WORDS = [
#         "สูตร", "ผสม", "แปรรูป", "เส้น", "แป้ง", "ขนม", "ขนมจีน", "บะหมี่", "พาสต้า", 
#         "น้ำ", "ซอส", "ผง", "แหนม", "ไส้กรอก", "กุนเชียง", "ลูกชิ้น", "ข้าว", "ข้าวหอม", 
#         "โจ๊ก", "ข้าวต้ม", "ซุป", "porridge", "soup", "broth", "chowder",
#         "mix", "mixed", "powder", "sauce", "noodle", "pasta", "snack", "processed",
#         "sausage", "bites", "rice", "jasmine", "stick", "chip", "roll", "cracker",
#         "nugget", "burger", "marinated", "pickled", "dry", "dried", "อบแห้ง"
#     ]

#     # 🎯 SPECIFICITY RULES
#     SPEC_RULES = [
#         # ✅ EGGS: Strict Block Quail
#         {"triggers": ["ไข่ไก่", "chicken egg", "egg", "ไข่"], 
#          "must": ["ไข่", "egg"], 
#          "block": ["quail", "กระทา", "เยี่ยวม้า", "century", "เค็ม", "salted", "liquid", "white", "yolk"]},

#         # ✅ COKE: Strict Block Sprite
#         {"triggers": ["coke zero", "โค้กซีโร่", "โค้ก zero"], 
#          "must": ["coke", "zero", "โค้ก", "ซีโร่", "cola", "ไม่มีน้ำตาล"], 
#          "block": ["sprite", "สไปรท์", "fanta", "แฟนก้า", "pepsi", "เป๊ปซี่", "schweppes", "est", "เอส"]},

#         # Meat/Fish
#         {"triggers": ["สามชั้น", "belly"], "must": ["สามชั้น", "belly"], "block": []},
#         {"triggers": ["สันคอ", "collar"], "must": ["สันคอ", "collar"], "block": []},
#         {"triggers": ["สันนอก", "loin"], "must": ["สันนอก", "loin"], "block": ["ใน", "tender"]},
#         {"triggers": ["สันใน", "tenderloin"], "must": ["สันใน", "tenderloin"], "block": ["นอก", "sirloin"]},
#         {"triggers": ["หมูบด", "minced", "ground"], "must": ["บด", "minced", "ground"], "block": ["slice", "ชิ้น"]},
#         {"triggers": ["ซี่โครง", "rib"], "must": ["ซี่โครง", "rib"], "block": ["แหนม"]},
#         {"triggers": ["อกไก่", "breast"], "must": ["อก", "breast"], "block": ["น่อง", "drumstick"]},
#         {"triggers": ["น่อง", "drumstick"], "must": ["น่อง", "drumstick"], "block": ["ปีก", "wing", "อก", "breast"]},
#         {"triggers": ["ปีก", "wing"], "must": ["ปีก", "wing", "กลาง", "บน"], "block": []},
#         {"triggers": ["สะโพก", "thigh"], "must": ["สะโพก", "thigh"], "block": []},
#         {"triggers": ["ทับทิม", "tabtim", "red tilapia"], "must": ["ทับทิม", "red tilapia", "ruby"], "block": ["นิล", "black"]},
#         {"triggers": ["นิล", "tilapia"], "must": ["นิล", "tilapia"], "block": ["ทับทิม", "red"]},
#         {"triggers": ["salmon", "แซลมอน"], "must": ["salmon", "แซลมอน"], "block": ["head", "bone", "scrap", "หัว", "กาง"]},
#         {"triggers": ["dory", "ดอรี่"], "must": ["dory", "ดอรี่", "pangasius"], "block": []},
#         {"triggers": ["saba", "ซาบะ"], "must": ["saba", "ซาบะ"], "block": ["noodle", "bento"]},
#         {"triggers": ["apple", "แอปเปิ้ล"], "must": ["apple", "แอปเปิ้ล"], "block": ["juice", "cider", "pie", "น้ำ"]},
#         {"triggers": ["orange", "ส้ม"], "must": ["orange", "ส้ม"], "block": ["juice", "น้ำ"]},
#     ]

#     active_musts = []
#     active_blocks = []
    
#     for rule in SPEC_RULES:
#         if any(t in q for t in rule["triggers"]):
#             active_musts.extend(rule["must"])
#             active_blocks.extend(rule["block"])

#     is_fresh_query = any(w in q for w in ["หมู", "ไก่", "เนื้อ", "ปลา", "ผัก", "ผลไม้", "pork", "chicken", "beef", "fish", "veg", "fruit", "salmon", "แซลมอน"])

#     egg_grade = None
#     m = re.search(r"(?:เบอร์|no[\.\s]|number|size)\s*(\d)", q)
#     if m: egg_grade = m.group(1)

#     cleaned = []

#     for r in results:
#         raw_name = str(r.get("Product Name", ""))
#         name = _norm(raw_name)
#         if not name: continue
        
#         if len(re.sub(r"[^\d]", "", name)) > 4 and len(name) < 15: continue

#         if any(w in name for w in PET_WORDS): continue
#         if any(w in name for w in NON_FOOD_WORDS): continue
#         if any(w in name for w in COOKED_WORDS): continue
        
#         if is_fresh_query:
#             if any(w in name for w in PROCESSED_WORDS): continue
#             if any(w in name for w in BABY_FOOD_WORDS): continue

#         # ✅ TYPO FIXED HERE: 'n' -> 'name'
#         if "coke" in q or "โค้ก" in q:
#             if any(w in name for w in NON_FOOD_WORDS): continue

#         if active_musts:
#             if not any(w in name for w in active_musts): continue
#         if active_blocks:
#             if any(w in name for w in active_blocks): continue

#         if egg_grade:
#             found_grades = re.findall(r"(?:เบอร์|no[\.\s]|number|size)\s*(\d)", name)
#             if found_grades and egg_grade not in found_grades: continue

#         cleaned.append(r)

#     return cleaned

# def best_per_retailer(item: str, deals: List[dict]) -> List[dict]:
#     best: Dict[str, dict] = {}
#     for d in deals:
#         retailer = d.get("WINNER", "Unknown")
#         try: unit_price = float(d.get("Unit Price", 999999))
#         except: unit_price = 999999.0

#         if retailer not in best or unit_price < float(best[retailer].get("Unit Price", 999999)):
#             best[retailer] = d

#     out = []
#     for retailer, d in best.items():
#         unit = d.get("BaseUnit", "unit")
#         try: raw_price = float(d.get("Price", 0))
#         except: raw_price = 0.0
#         try: raw_unit_price = float(d.get("Unit Price", 0))
#         except: raw_unit_price = 0.0
#         try: original_price = float(d.get("Original Price", raw_price))
#         except: original_price = raw_price
        
#         is_promo = original_price > raw_price

#         out.append({
#             "WINNER": retailer,
#             "Product Name": d.get("Product Name", ""),
#             "Product Type": "",
#             "Best Price": f"฿{raw_price:.2f}",
#             "Unit Price": f"฿{raw_unit_price:.2f}/{unit}",
#             "_raw_price": raw_price,
#             "_raw_unit_price": raw_unit_price,
#             "is_promo": is_promo,
#             "original_price": original_price if is_promo else None,
#             "query_item": item,
#         })
#     out.sort(key=lambda x: float(x.get("_raw_unit_price", 999999)))
#     return out

# def expand_query_for_bigc(query: str) -> List[str]:
#     q = query.lower().strip()
#     expanded = [query]

#     if q in ["coke zero", "coca cola zero", "โค้ก zero", "โค้กซีโร่"]:
#         expanded += ["โค้ก สูตรไม่มีน้ำตาล", "โค้ก ไม่มีน้ำตาล", "coke no sugar"]

#     if "สันคอ" in q or "collar" in q: 
#         expanded += ["หมูสันคอ", "เนื้อหมูสันคอ", "s-pure สันคอ", "betagro สันคอ"]
#     if "สามชั้น" in q or "belly" in q: 
#         expanded += ["หมูสามชั้น", "เนื้อหมูสามชั้น", "s-pure สามชั้น", "betagro สามชั้น"]
#     if "สันนอก" in q or "loin" in q: 
#         expanded += ["หมูสันนอก", "เนื้อหมูสันนอก"]
#     if "บด" in q or "minced" in q: 
#         expanded += ["หมูบด", "เนื้อหมูบด"]

#     if "อกไก่" in q or "breast" in q: 
#         expanded += ["เนื้ออกไก่", "อกไก่ลอกหนัง", "s-pure อกไก่"]
#     if "น่อง" in q or "drumstick" in q: 
#         expanded += ["น่องไก่", "ปีกบน"]

#     if "ไข่" in q and "เบอร์" in q:
#         expanded.append(q.replace("เบอร์", "เบอร์ที่"))

#     return list(dict.fromkeys(expanded))

# async def process_single_item(item: str) -> List[dict]:
#     print(f"🔎 Processing: {item}")
#     scrape_tasks = []
    
#     for t in TARGETS:
#         queries = [item]
#         if t["name"] == "BigC":
#             queries = expand_query_for_bigc(item)
            
#         for q in queries:
#             scrape_tasks.append(scrape_search(t["name"], t["search_url"], q, t["selectors"]))

#     results_lists = await asyncio.gather(*scrape_tasks, return_exceptions=True)
#     raw_data = []
#     for res in results_lists:
#         if isinstance(res, list): raw_data.extend(res)

#     cleaned_data = clean_search_results(item, raw_data)
#     if not cleaned_data: return []

#     try:
#         df = pd.DataFrame(cleaned_data)
#         processed = find_best_deals(df)
#         candidates = json.loads(processed.to_json(orient="records"))
        
#         engine = SmartMatcher(candidates)
#         matches = engine.find_matches(item, threshold=0.25)
#         matches = clean_search_results(item, matches) 
#         if not matches: matches = candidates

#         return best_per_retailer(item, matches[:60])
#     except Exception as e:
#         print(f"❌ Core Logic Error: {e}")
#         return []

# @app.post("/api/compare")
# async def compare_prices(req: CompareRequest):
#     final_results = []
#     for item in req.items:
#         item = (item or "").strip()
#         if not item: continue
#         results = await process_single_item(item)
#         final_results.extend(results)
#     return {"status": "success", "message": "", "data": final_results}
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)