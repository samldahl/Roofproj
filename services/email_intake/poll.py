"""Gmail poller: every 5 min, look for replies to DPA threads, download
attachments to S3, enqueue normalize jobs.

Matches inbound messages by:
  - threadId in outreach_requests.gmail_thread_id, OR
  - sender domain in cities.contact_email
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime

import boto3
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pymongo import MongoClient

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
ATTACHMENT_EXTS = (".xls", ".xlsx", ".csv", ".pdf")


def gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def find_city_for_message(db, msg) -> str | None:
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    sender = headers.get("From", "").lower()

    req = db.outreach_requests.find_one({"gmail_thread_id": msg["threadId"]})
    if req:
        return req["city_slug"]

    for c in db.cities.find({}, {"slug": 1, "contact_email": 1}):
        email = (c.get("contact_email") or "").lower()
        if email and email in sender:
            return c["slug"]
    return None


def process_message(svc, db, s3, msg_id: str) -> None:
    msg = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    slug = find_city_for_message(db, msg)
    if not slug:
        return

    for part in msg["payload"].get("parts", []):
        fn = part.get("filename") or ""
        if not fn.lower().endswith(ATTACHMENT_EXTS):
            continue
        att_id = part["body"].get("attachmentId")
        if not att_id:
            continue
        att = svc.users().messages().attachments().get(
            userId="me", messageId=msg_id, id=att_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])

        s3_key = f"raw/{slug}/email/{msg_id}/{fn}"
        s3.put_object(Bucket=os.environ["S3_BUCKET"], Key=s3_key, Body=data)
        db.jobs.insert_one({
            "type": "normalize",
            "status": "queued",
            "city_slug": slug,
            "s3_key": s3_key,
            "claim_at": None,
            "created_at": datetime.utcnow(),
        })
        db.outreach_requests.update_one(
            {"gmail_thread_id": msg["threadId"]},
            {"$set": {"status": "received", "received_at": datetime.utcnow()}},
        )
        print(f"intake city={slug} file={fn}")


def main() -> None:
    load_dotenv()
    db = MongoClient(os.environ["MONGO_URI"])[os.getenv("MONGO_DB", "roofproj")]
    svc = gmail_service()
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT") or None,
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.getenv("S3_REGION", "auto"),
    )
    seen_history_id = None
    print("email intake started")
    while True:
        try:
            res = svc.users().messages().list(
                userId="me", q="has:attachment newer_than:7d", maxResults=50
            ).execute()
            for m in res.get("messages", []):
                # idempotency: skip if any source_file already references this msg id
                if db.jobs.find_one({"s3_key": {"$regex": f"/email/{m['id']}/"}}):
                    continue
                process_message(svc, db, s3, m["id"])
        except Exception as e:
            print(f"intake error: {e}")
        time.sleep(300)


if __name__ == "__main__":
    main()
