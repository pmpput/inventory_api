from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
import re

# ==================================================
# MODEL LOADER (SINGLETON)
# ==================================================
_model_instance = None

def get_model():
    global _model_instance
    if _model_instance is None:
        print("🤖 Loading AI Model...")
        _model_instance = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )
        print("✅ Model Loaded")
    return _model_instance


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# ==================================================
# SMART MATCHER (RESTAURANT SAFE)
# ==================================================
class SmartMatcher:
    def __init__(self, scraped_data: list):
        self.df = pd.DataFrame(scraped_data)
        self.model = get_model()
        self.vectors = None

        if not self.df.empty:
            self.df["search_text"] = self.df["Product Name"].astype(str)
            self.vectors = self.model.encode(
                self.df["search_text"].tolist()
            )

    # ==================================================
    # 🔒 STRICT FILTER (DOMAIN-AWARE)
    # ==================================================
    def _strict_filter(self, query: str, candidates: pd.DataFrame) -> pd.DataFrame:
        q = _norm(query)

        # ----------------------------
        # GLOBAL HARD BLOCK
        # ----------------------------
        BLOCK_ALWAYS = [
            "ชาม", "เครื่อง", "บดอาหาร", "food processor",
            "เครื่องครัว", "อุปกรณ์", "bowl", "mixer",
            "cat", "dog", "pet", "อาหารสัตว์",
            "baby", "อาหารเด็ก"
        ]

        # ----------------------------
        # ANIMAL LOCK
        # ----------------------------
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

        # ----------------------------
        # CUT / PART LOCK
        # ----------------------------
        CUT_RULES = []

        if "สันคอ" in q or "collar" in q:
            CUT_RULES.append({
                "must": ["สันคอ", "collar"],
                "block": ["ไก่", "chicken", "สะโพก", "thigh"]
            })

        if any(w in q for w in ["หมูบด", "minced", "ground"]):
            CUT_RULES.append({
                "must": ["บด", "minced", "ground"],
                "block": ["ชาม", "เครื่อง", "food", "processor"]
            })

        out = []

        for _, row in candidates.iterrows():
            name = _norm(row.get("Product Name", ""))

            # HARD BLOCK
            if any(w in name for w in BLOCK_ALWAYS):
                continue

            # ANIMAL LOCK
            if active_animal:
                if not any(w in name for w in active_animal):
                    continue

            # CUT LOCK
            rejected = False
            for r in CUT_RULES:
                if r.get("must") and not any(w in name for w in r["must"]):
                    rejected = True
                if r.get("block") and any(w in name for w in r["block"]):
                    rejected = True
                if rejected:
                    break

            if rejected:
                continue

            out.append(row)

        if not out:
            return candidates.iloc[0:0].copy()

        return pd.DataFrame(out).copy()

    # ==================================================
    # 🧠 AI MATCHING
    # ==================================================
    def find_matches(self, user_query: str, threshold=0.28):
        if self.vectors is None or self.df.empty:
            return []

        q = user_query.strip()
        if not q:
            return []

        query_vec = self.model.encode([q])
        scores = cosine_similarity(query_vec, self.vectors)[0]

        df = self.df.copy()
        df["score"] = scores

        candidates = df[df["score"] >= threshold]
        if candidates.empty:
            return []

        candidates = self._strict_filter(q, candidates)
        if candidates.empty:
            return []

        keywords = _norm(q).split()

        def boost(row):
            s = float(row["score"])
            name = _norm(row["Product Name"])
            for w in keywords:
                if len(w) >= 2 and w in name:
                    s += 0.25
            return s

        candidates["final_score"] = candidates.apply(boost, axis=1)

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