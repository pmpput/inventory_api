# import re

# def detect_intent(query: str):
#     q = query.lower()

#     intent = {
#         "category": None,
#         "animal": None,
#         "part": None,
#         "state": "raw",
#     }

#     # --------------------
#     # CATEGORY
#     # --------------------
#     if any(w in q for w in ["coke", "cola", "โค้ก", "น้ำอัดลม"]):
#         intent["category"] = "drink"
#     elif any(w in q for w in ["หมู", "ไก่", "เนื้อ", "ปลา", "pork", "chicken", "beef", "fish"]):
#         intent["category"] = "meat"
#     elif any(w in q for w in ["ผัก", "vegetable", "veg"]):
#         intent["category"] = "vegetable"
#     else:
#         intent["category"] = "grocery"

#     # --------------------
#     # ANIMAL
#     # --------------------
#     ANIMALS = {
#         "pork": ["หมู", "pork"],
#         "chicken": ["ไก่", "chicken"],
#         "beef": ["เนื้อ", "beef"],
#         "salmon": ["แซลมอน", "salmon"],
#         "fish": ["ปลา", "fish"],
#     }

#     for a, words in ANIMALS.items():
#         if any(w in q for w in words):
#             intent["animal"] = a
#             break

#     # --------------------
#     # PART / CUT
#     # --------------------
#     PARTS = {
#         "collar": ["สันคอ", "collar"],
#         "belly": ["สามชั้น", "belly"],
#         "loin": ["สันใน", "loin"],
#         "rib": ["ซี่โครง", "rib"],
#         "head": ["หัว"],
#         "bone": ["กระดูก", "bone"],
#         "wing": ["ปีก", "wing"],
#         "breast": ["อก", "breast"],
#         "thigh": ["สะโพก", "thigh"],
#     }

#     for p, words in PARTS.items():
#         if any(w in q for w in words):
#             intent["part"] = p
#             break

#     # --------------------
#     # STATE
#     # --------------------
#     if any(w in q for w in ["ทอด", "ย่าง", "ต้ม", "สุก", "cooked"]):
#         intent["state"] = "cooked"
#     elif any(w in q for w in ["แช่แข็ง", "frozen"]):
#         intent["state"] = "frozen"

#     return intent