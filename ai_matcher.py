import asyncio
import os
import json
import re
import pandas as pd
from typing import List, Dict, Any
from pydantic import BaseModel

# IMPORT YOUR SCRAPERS
from retailer_scraper import scrape_search, find_best_deals
from ai_matcher import SmartMatcher

# ==========================================
# 🔧 CONFIG
# ==========================================
TARGETS = [
    {
        "name": "BigC",
        "search_url": "https://www.bigc.co.th/en/search?q={q}",
        "selectors": {"product_card": 'div.productItem, div[data-testid="product-card"]', "name": ".product-name", "price": ".product-price"},
    },
    {
        "name": "Tops",
        "search_url": "https://www.tops.co.th/en/search/{q}",
        "selectors": {"product_card": ".product-item-info", "name": ".product-item-link", "price": ".price"},
    },
    {
        "name": "Makro",
        "search_url": "https://www.makro.pro/en/c/search?q={q}",
        "selectors": {"product_card": 'div[class*="product-card"]', "name": 'span[class*="name"]', "price": 'span[class*="price"]'},
    },
]

class CompareRequest(BaseModel):
    items: List[str]

# ==========================================
# 🧠 CORE LOGIC
# ==========================================
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def clean_search_results(query: str, results: List[dict]) -> List[dict]:
    """กรองสินค้าที่ไม่เกี่ยวข้องออก เช่น อาหารสัตว์ ของใช้ หรืออาหารเด็ก"""
    q = _norm(query)
    # ... (ส่วนของลิสต์คำที่ใช้กรอง เช่น PET_WORDS, NON_FOOD_WORDS ให้คงเดิมตามโค้ดคุณ)
    
    cleaned = []
    for r in results:
        raw_name = str(r.get("Product Name", ""))
        name = _norm(raw_name)
        if not name: continue
        
        # เพิ่ม Logic การกรองเบื้องต้น
        if any(w in name for w in ["ชาม", "อุปกรณ์", "ของเล่น", "mixer"]): continue #
        
        cleaned.append(r)
    return cleaned

async def process_single_item(item: str) -> List[dict]:
    """ประมวลผลสินค้า 1 รายการ ค้นหาทุกห้าง และจัดอันดับดีลที่ดีที่สุด"""
    print(f"🔎 Processing: {item}")
    scrape_tasks = []
    
    for t in TARGETS:
        queries = [item]
        if t["name"] == "BigC":
            from grocery_api import expand_query_for_bigc # เรียกใช้ helper
            queries = expand_query_for_bigc(item)
            
        for q in queries:
            scrape_tasks.append(scrape_search(t["name"], t["search_url"], q, t["selectors"]))

    # 🚀 รัน Scrapers ขนานกันสำหรับ 1 สินค้า (ห้างละ 1 หน้าต่าง)
    results_lists = await asyncio.gather(*scrape_tasks, return_exceptions=True)
    raw_data = []
    for res in results_lists:
        if isinstance(res, list): raw_data.extend(res)

    # 1. Clean ข้อมูลเบื้องต้น
    cleaned_data = clean_search_results(item, raw_data)
    if not cleaned_data: return []

    try:
        # 2. ใช้ SmartMatcher (TF-IDF) เพื่อจัดอันดับความเกี่ยวข้อง
        engine = SmartMatcher(cleaned_data)
        matches = engine.find_matches(item, threshold=0.01) # ใช้ threshold ต่ำเพื่อให้ข้อมูลออกไปก่อน
        
        if not matches:
            matches = cleaned_data

        # 3. สรุปดีลที่ถูกที่สุดต่อห้าง
        final_deals = best_per_retailer(item, matches)
        
        # 🚀 จุดสำคัญ: ใส่ queryItem กลับไปเพื่อให้ Flutter กรองชื่อสินค้าได้ตรงช่อง
        for d in final_deals:
            d["queryItem"] = item 
            
        return final_deals
    except Exception as e:
        print(f"❌ Core Logic Error for {item}: {e}")
        return []

def best_per_retailer(item: str, deals: List[dict]) -> List[dict]:
    """เลือกสินค้าที่คุ้มที่สุดจากแต่ละห้าง (1 ห้าง 1 ดีล)"""
    best: Dict[str, dict] = {}
    for d in deals:
        retailer = d.get("WINNER", "Unknown")
        # ใช้ Unit Price ในการตัดสินความคุ้มค่า
        u_price = float(d.get("Unit Price", 999999))

        if retailer not in best or u_price < float(best[retailer].get("Unit Price", 999999)):
            best[retailer] = d

    out = []
    for retailer, d in best.items():
        out.append({
            "retailer": retailer,
            "productName": d.get("Product Name", ""),
            "price": float(d.get("Price", 0)),
            "unitPrice": float(d.get("Unit Price", 0)),
            "baseUnit": d.get("BaseUnit", "unit"),
            "queryItem": item,
        })
    return out

def expand_query_for_bigc(query: str) -> List[str]:
    """ขยายคำค้นหาเฉพาะ BigC เพราะ Search Engine ห้างนี้ต้องการคำที่เจาะจง"""
    q = query.lower().strip()
    expanded = [query]
    # ... (Logic การขยายคำค้นหา หมูบด -> เนื้อหมูบด ให้คงเดิม)
    return list(dict.fromkeys(expanded))