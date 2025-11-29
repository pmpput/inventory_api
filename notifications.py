import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

def send_fcm_to_tokens(tokens: list[str], title: str, body: str, data: dict | None = None):
    if not tokens:
        return None
    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    resp = messaging.send_multicast(message)
    print(f"✅ ส่งแจ้งเตือนสำเร็จ {resp.success_count} เครื่อง, ล้มเหลว {resp.failure_count} เครื่อง")
    return resp