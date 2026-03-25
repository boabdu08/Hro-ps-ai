import json
import urllib.request


def post_json(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())


def main():
    base = "http://127.0.0.1:8000"

    admin = post_json(f"{base}/auth/login", {"tenant": "demo-hospital", "username": "admin1", "password": "123456"})
    doctor = post_json(f"{base}/auth/login", {"tenant": "demo-hospital", "username": "doctor1", "password": "123456"})
    nurse = post_json(f"{base}/auth/login", {"tenant": "demo-hospital", "username": "nurse1", "password": "123456"})

    admin_tok = admin["access_token"]
    doctor_tok = doctor["access_token"]
    nurse_tok = nurse["access_token"]

    # Send to all staff in ER so both doctor + nurse can see it.
    sent = post_json(
        f"{base}/messages/send",
        {
            "sender_role": "admin",
            "sender_name": "Hospital Admin",
            "target_role": "all",
            "target_department": "ER",
            "priority": "high",
            "message_type": "alert",
            "title": "Test Per-User Read",
            "message": "If you read this as doctor, nurse should still see it unread.",
        },
        token=admin_tok,
    )

    mid = sent["data"]["message_id"]
    inbox_url = f"{base}/messages?department=ER&include_archived=false&limit=20"

    doc_msgs_before = get_json(inbox_url, token=doctor_tok)
    doc_msg_before = [m for m in doc_msgs_before["messages"] if m["message_id"] == mid][0]

    nurse_msgs_before = get_json(inbox_url, token=nurse_tok)
    nurse_msg_before = [m for m in nurse_msgs_before["messages"] if m["message_id"] == mid][0]

    post_json(f"{base}/messages/ack", {"message_id": mid}, token=doctor_tok)

    doc_msgs_after = get_json(inbox_url, token=doctor_tok)
    doc_msg_after = [m for m in doc_msgs_after["messages"] if m["message_id"] == mid][0]

    nurse_msgs_after = get_json(inbox_url, token=nurse_tok)
    nurse_msg_after = [m for m in nurse_msgs_after["messages"] if m["message_id"] == mid][0]

    print("message_id=", mid)
    print("doctor_before.is_read=", doc_msg_before.get("is_read"), "unread_count=", doc_msgs_before.get("unread_count"))
    print("doctor_after.is_read=", doc_msg_after.get("is_read"), "unread_count=", doc_msgs_after.get("unread_count"))
    print("nurse_before.is_read=", nurse_msg_before.get("is_read"), "unread_count=", nurse_msgs_before.get("unread_count"))
    print("nurse_after.is_read=", nurse_msg_after.get("is_read"), "unread_count=", nurse_msgs_after.get("unread_count"))


if __name__ == "__main__":
    main()
