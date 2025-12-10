# firebase_utils.py
import os
import json

import firebase_admin
from firebase_admin import credentials, messaging

_app = None  # cache app

def get_firebase_app():
    """
    Initialize Firebase แค่ตอนจำเป็น และทำครั้งเดียว
    """
    global _app
    if _app is not None:
        return _app

    firebase_json = os.getenv("FIREBASE_CREDENTIALS")

    if firebase_json:
        # Running on Render / Cloud
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        _app = firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized from FIREBASE_CREDENTIALS env")
        return _app

    # Running on local – ใช้ไฟล์ serviceAccountKey.json
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        _app = firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized from serviceAccountKey.json")
        return _app

    print("⚠️ Firebase not initialized (no credentials)")
    return None


def send_inventory_notification(title: str, body: str):
    """
    Helper ส่ง FCM แบบเบา ๆ
    """
    app = get_firebase_app()
    if app is None:
        print(f"⚠️ Skip FCM: {title} - {body}")
        return

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            topic="inventory_alerts",
        )
        messaging.send(message)
        print(f"📢 ส่งแจ้งเตือนแล้ว: {title} - {body}")
    except Exception as e:
        print(f"❌ แจ้งเตือนล้มเหลว: {e}")
