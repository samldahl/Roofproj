"""Outreach worker: claims outreach_send jobs, renders DPA template,
sends via Gmail API as Tony's user. Respects OUTREACH_ENABLED kill switch
and OUTREACH_DAILY_CAP throttle.
"""
from __future__ import annotations

import base64
import os
import time
import traceback
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

import yaml
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from jinja2 import Template
from pymongo import MongoClient

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CITIES_DIR = Path(__file__).resolve().parents[2] / "cities"
TEMPLATE = (Path(__file__).parent / "templates" / "dpa_request.txt").read_text()


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


def render_email(city: dict, sender_email: str) -> tuple[str, str]:
    rendered = Template(TEMPLATE).render(
        city_name=city["name"],
        start_date="January 1, 2005",
        sender_name=os.getenv("SENDER_NAME", "Proficient Construction"),
        sender_email=sender_email,
    )
    lines = rendered.splitlines()
    subject = lines[0].replace("Subject:", "").strip()
    body = "\n".join(lines[2:]).strip()
    return subject, body


def send_dpa(svc, city: dict, sender_email: str) -> dict:
    subject, body = render_email(city, sender_email)
    msg = MIMEText(body)
    msg["to"] = city["contact_email"]
    msg["from"] = sender_email
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return svc.users().messages().send(userId="me", body={"raw": raw}).execute()


def today_send_count(db) -> int:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.outreach_requests.count_documents({"sent_at": {"$gte": start}})


def claim_job(db):
    now = datetime.utcnow()
    return db.jobs.find_one_and_update(
        {
            "type": "outreach_send",
            "status": {"$in": ["queued", "running"]},
            "$or": [{"claim_at": None}, {"claim_at": {"$lt": now}}],
        },
        {"$set": {"status": "running", "claim_at": now + timedelta(minutes=5)}},
        sort=[("created_at", 1)],
    )


def run_job(svc, db, job: dict, sender_email: str) -> None:
    slug = job["city_slug"]
    with (CITIES_DIR / f"{slug}.yaml").open() as f:
        city = yaml.safe_load(f)
    if not city.get("contact_email"):
        raise ValueError(f"{slug} has no contact_email")

    result = send_dpa(svc, city, sender_email)
    now = datetime.utcnow()
    db.outreach_requests.insert_one({
        "city_slug": slug,
        "sent_at": now,
        "gmail_message_id": result["id"],
        "gmail_thread_id": result["threadId"],
        "follow_up_at": now + timedelta(days=14),  # ~10 business days
        "status": "sent",
    })
    db.jobs.update_one(
        {"_id": job["_id"]},
        {"$set": {"status": "done", "finished_at": now, "result": result}},
    )


def enqueue_auto_sends(db) -> int:
    """Cron-style: for auto_send cities, queue if no outreach in last 6 months."""
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    queued = 0
    for c in db.cities.find({"auto_send": True, "status": "active"}):
        recent = db.outreach_requests.find_one({
            "city_slug": c["slug"], "sent_at": {"$gte": six_months_ago}
        })
        if recent:
            continue
        existing = db.jobs.find_one({
            "type": "outreach_send",
            "city_slug": c["slug"],
            "status": {"$in": ["queued", "running"]},
        })
        if existing:
            continue
        db.jobs.insert_one({
            "type": "outreach_send",
            "status": "queued",
            "city_slug": c["slug"],
            "claim_at": None,
            "created_at": datetime.utcnow(),
        })
        queued += 1
    return queued


def main() -> None:
    load_dotenv()
    db = MongoClient(os.environ["MONGO_URI"])[os.getenv("MONGO_DB", "roofproj")]
    svc = gmail_service()
    sender_email = os.environ["GMAIL_SENDER"]
    cap = int(os.getenv("OUTREACH_DAILY_CAP", "5"))
    print("outreach worker started")

    last_auto_scan = 0.0
    while True:
        if os.getenv("OUTREACH_ENABLED", "false").lower() != "true":
            time.sleep(30)
            continue

        # Periodically scan for auto-send candidates
        if time.time() - last_auto_scan > 3600:
            queued = enqueue_auto_sends(db)
            if queued:
                print(f"auto-queued {queued} cities")
            last_auto_scan = time.time()

        if today_send_count(db) >= cap:
            time.sleep(300)
            continue

        job = claim_job(db)
        if not job:
            time.sleep(10)
            continue

        try:
            run_job(svc, db, job, sender_email)
            print(f"sent DPA to {job['city_slug']}")
        except Exception:
            db.jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"status": "failed", "error": traceback.format_exc(),
                          "finished_at": datetime.utcnow()}},
            )
            print(f"send failed: {job['city_slug']}")
        time.sleep(60)  # gentle pacing between sends


if __name__ == "__main__":
    main()
