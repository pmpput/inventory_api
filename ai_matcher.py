import pandas as pd
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ==================================================
# 🔧 LIGHTWEIGHT UTILS
# ==================================================
def _norm(s: str) -> str:
    if s is None:
        return ""
    s = re.sub(r"\s+", " ", str(s)).strip().lower()
    return s

# ==================================================
# SMART MATCHER (TF-IDF VERSION - RAM FRIENDLY)
# ==================================================
class SmartMatcher:
    def __init__(self, scraped_data: list):
        self.df = pd.DataFrame(scraped_data)
        
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb', 
            ngram_range=(2, 4),
            min_df=1
        )
        self.vectors = None

        if not self.df.empty:
            self.df["search_text"] = self.df["Product Name"].apply(_norm)
            self.vectors = self.vectorizer.fit_transform(self.df["search_text"].tolist())

    # ==================================================
    # 🧠 MATCHING LOGIC
    # ==================================================
    def find_matches(self, user_query: str, threshold=0.01):
        """
        ค้นหาและจับคู่สินค้า 
        ปรับ threshold เป็น 0.01 เพื่อให้ข้อมูลแสดงผลได้ง่ายขึ้นบน Render
        """
        if self.vectors is None or self.df.empty:
            return []

        q = _norm(user_query)
        if not q:
            return []

        # 1. แปลง Query และคำนวณคะแนน
        query_vec = self.vectorizer.transform([q])
        scores = cosine_similarity(query_vec, self.vectors)[0]

        df_result = self.df.copy()
        df_result["score"] = scores

        # 2. 🔍 DEBUG: ตรวจสอบคะแนนสูงสุด 3 อันดับแรก (ดูใน Log ของ Render)
        top_candidates = df_result.sort_values(by="score", ascending=False).head(3)
        for _, r in top_candidates.iterrows():
            print(f"DEBUG Match: Query[{q}] -> Item[{r['Product Name']}] Score: {r['score']}")
        
        # 3. กรองตาม Threshold
        candidates = df_result[df_result["score"] >= threshold].copy()
        
        if candidates.empty:
            return []

        # 4. ใช้ Strict Filter (หากยังไม่แสดงผล ให้ลอง Comment บรรทัดนี้ออกเพื่อทดสอบ)
        candidates = self._strict_filter(user_query, candidates)
        
        if candidates.empty:
            return []

        # 5. 🎯 Keyword Boosting
        keywords = q.split()
        def boost_score(row):
            current_score = float(row["score"])
            product_name = _norm(row["Product Name"])
            for word in keywords:
                if len(word) >= 2 and word in product_name:
                    current_score += 0.50 # เพิ่มคะแนนพิเศษให้คำที่ตรงกัน
            return current_score

        candidates["final_score"] = candidates.apply(boost_score, axis=1)

        # 6. จัดลำดับผลลัพธ์
        if "Unit Price" in candidates.columns:
            candidates = candidates.sort_values(
                by=["final_score", "Unit Price"],
                ascending=[False, True]
            )
        else:
            candidates = candidates.sort_values(by="final_score", ascending=False)

        return candidates.to_dict(orient="records")

    # ==================================================
    # 🔒 STRICT FILTER (กรองประเภทสินค้า)
    # ==================================================
    def _strict_filter(self, query: str, candidates: pd.DataFrame) -> pd.DataFrame:
        q = _norm(query)
        BLOCK_ALWAYS = ["ชาม", "เครื่อง", "บดอาหาร", "food processor", "เครื่องครัว", "อุปกรณ์", "bowl", "mixer", "cat", "dog", "pet", "อาหารสัตว์", "baby", "อาหารเด็ก"]

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
            if any(w in name for w in BLOCK_ALWAYS):
                continue
            if active_animal:
                if not any(w in name for w in active_animal):
                    continue
            out.append(row)

        return pd.DataFrame(out) if out else candidates.iloc[0:0].copy()