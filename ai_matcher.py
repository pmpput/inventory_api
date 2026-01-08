# ai_matcher.py
import pandas as pd
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ==================================================
# 🔧 LIGHTWEIGHT UTILS
# ==================================================
def _norm(s: str) -> str:
    """ทำความสะอาดข้อความ ลบช่องว่าง และทำให้เป็นตัวพิมพ์เล็ก"""
    if s is None:
        return ""
    # ลบช่องว่างซ้ำๆ และตัดช่องว่างหัวท้าย
    s = re.sub(r"\s+", " ", str(s)).strip().lower()
    return s

# ==================================================
# SMART MATCHER (TF-IDF VERSION - RAM FRIENDLY)
# ==================================================
class SmartMatcher:
    def __init__(self, scraped_data: list):
        self.df = pd.DataFrame(scraped_data)
        
        # ใช้ TfidfVectorizer แบบ Character N-grams (2-4 ตัวอักษร)
        # วิธีนี้ช่วยให้ระบบเข้าใจภาษาไทยได้โดยไม่ต้องใช้ AI Model ขนาดใหญ่
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb', 
            ngram_range=(2, 4),
            min_df=1
        )
        self.vectors = None

        if not self.df.empty:
            # เตรียมข้อความสำหรับการทำ Vectorization
            self.df["search_text"] = self.df["Product Name"].apply(_norm)
            # สร้างฐานข้อมูลความหมาย (Vector Space)
            self.vectors = self.vectorizer.fit_transform(self.df["search_text"].tolist())

    # ==================================================
    # 🧠 MATCHING LOGIC
    # ==================================================
    def find_matches(self, user_query: str, threshold=0.05):
        """
        ค้นหาสินค้าที่ใกล้เคียงที่สุดโดยใช้ TF-IDF 
        ใช้ RAM น้อยกว่า 10MB (เหมาะสำหรับ Render Free)
        """
        if self.vectors is None or self.df.empty:
            return []

        q = _norm(user_query)
        if not q:
            return []

        # แปลง User Query เป็น Vector
        query_vec = self.vectorizer.transform([q])
        
        # คำนวณ Cosine Similarity ระหว่าง Query กับฐานข้อมูล
        scores = cosine_similarity(query_vec, self.vectors)[0]

        df_result = self.df.copy()
        df_result["score"] = scores

        # กรองเอาเฉพาะรายการที่ผ่านเกณฑ์ (Threshold สำหรับ TF-IDF แนะนำที่ 0.1 - 0.2)
        candidates = df_result[df_result["score"] >= threshold]
        
        if candidates.empty:
            return []

        # ใช้ Strict Filter กรองตามเงื่อนไขธุรกิจ (เช่น ห้ามข้ามชนิดสัตว์)
        candidates = self._strict_filter(user_query, candidates)
        
        if candidates.empty:
            return []

        # 🎯 Keyword Boosting (ถ้าชื่อสินค้าตรงกับคำค้นหาเป๊ะๆ ให้คะแนนเพิ่ม)
        keywords = q.split()
        def boost_score(row):
            current_score = float(row["score"])
            product_name = _norm(row["Product Name"])
            for word in keywords:
                if len(word) >= 2 and word in product_name:
                    current_score += 0.20 # เพิ่มคะแนนพิเศษ
            return current_score

        candidates["final_score"] = candidates.apply(boost_score, axis=1)

        # จัดลำดับ: คะแนนสูงสุดก่อน ตามด้วยราคาที่ถูกที่สุด
        if "Unit Price" in candidates.columns:
            candidates = candidates.sort_values(
                by=["final_score", "Unit Price"],
                ascending=[False, True]
            )
        else:
            candidates = candidates.sort_values(by="final_score", ascending=False)

        return candidates.to_dict(orient="records")

    # ==================================================
    # 🔒 STRICT FILTER (DOMAIN-AWARE)
    # ==================================================
    def _strict_filter(self, query: str, candidates: pd.DataFrame) -> pd.DataFrame:
        q = _norm(query)
        
        # กรองของที่ไม่ใช่อาหารออก
        BLOCK_ALWAYS = [
            "ชาม", "เครื่อง", "บดอาหาร", "food processor",
            "เครื่องครัว", "อุปกรณ์", "bowl", "mixer",
            "cat", "dog", "pet", "อาหารสัตว์",
            "baby", "อาหารเด็ก"
        ]

        # กรองให้ตรงชนิดเนื้อสัตว์
        ANIMAL_RULES = {
            "pork": ["หมู", "pork"],
            "chicken": ["ไก่", "chicken"],
            "beef": ["เนื้อ", "beef"],
            "fish": ["ปลา", "fish"],
            "salmon": ["แซลมอน", "salmon"],
        }

        active_animal = None
        for animal, words in ANIMAL_RULES.items():
            if any(w in q for w in words):
                active_animal = words
                break

        out = []
        for _, row in candidates.iterrows():
            name = _norm(row.get("Product Name", ""))
            
            # 1. เช็ค Block list
            if any(w in name for w in BLOCK_ALWAYS):
                continue
            
            # 2. เช็คความถูกต้องของชนิดสัตว์
            if active_animal:
                if not any(w in name for w in active_animal):
                    continue
            
            out.append(row)

        if not out:
            return candidates.iloc[0:0].copy()

        return pd.DataFrame(out).copy()

    # ==================================================
    # 🧠 MATCHING LOGIC (TF-IDF Version)
    # ==================================================
    def find_matches(self, user_query: str, threshold=0.15):
        # 1. เช็คความพร้อมของข้อมูล
        if self.vectors is None or self.df.empty:
            return []

        q = _norm(user_query)
        if not q:
            return []

        # 2. แปลง Query เป็น TF-IDF Vector (แทนที่การใช้ self.model.encode)
        # วิธีนี้กิน RAM น้อยมากและไม่ต้องใช้ GPU
        query_vec = self.vectorizer.transform([q])
        
        # 3. คำนวณ Cosine Similarity ระหว่าง Query และสินค้าทั้งหมด
        scores = cosine_similarity(query_vec, self.vectors)[0]

        df = self.df.copy()
        df["score"] = scores

        # 4. กรองเบื้องต้นด้วย Threshold 
        # (TF-IDF มักใช้ค่าระหว่าง 0.1 - 0.2 ต่างจาก AI ที่ใช้ 0.3 ขึ้นไป)
        candidates = df[df["score"] >= threshold]
        if candidates.empty:
            return []

        # 5. กรองด้วย Strict Filter (ห้ามข้ามชนิดสัตว์, ห้ามของใช้)
        candidates = self._strict_filter(user_query, candidates)
        if candidates.empty:
            return []

        # 6. กระบวนการ Keyword Boosting (ส่วนสำคัญที่ทำให้ TF-IDF แม่นยำขึ้น)
        keywords = q.split()

        def boost(row):
            s = float(row["score"])
            name = _norm(row["Product Name"])
            # หากเจอคำค้นหาตรงๆ ในชื่อสินค้า ให้บวกคะแนนเพิ่มอย่างมีนัยสำคัญ
            for w in keywords:
                if len(w) >= 2 and w in name:
                    s += 0.20 # ปรับจาก 0.25 เป็น 0.20 ให้สมดุลกับคะแนน TF-IDF
            return s

        candidates["final_score"] = candidates.apply(boost, axis=1)

        # 7. จัดลำดับตามคะแนนความเหมือน และราคา (เรียงจากราคาถูกไปแพง)
        if "Unit Price" in candidates.columns:
            candidates = candidates.sort_values(
                by=["final_score", "Unit Price"],
                ascending=[False, True]
            )
        else:
            candidates = candidates.sort_values(
                by="final_score",
                ascending=False
            )

        return candidates.to_dict(orient="records")