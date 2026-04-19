#!/usr/bin/env python3
"""
rag/auto_updater.py
RAG自动更新引擎 — 运行在 .18
每周日 03:00 自动抓取曼省政府/联邦政府页面
检测内容变化 → 更新ChromaDB → Telegram通知

Cron (.18): 0 3 * * 0 /usr/bin/python3 /home/heng/super-ego-os/rag/auto_updater.py
"""
import os
import sys
import hashlib
import datetime
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rag.knowledge_base import get_collection
from common.db import db_cursor
from common.telegram_push import send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
HEADERS      = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

WATCH_PAGES = [
    {"id":"live_rent_assist",   "url":"https://www.gov.mb.ca/housing/assist/",                                                                                                              "topic":"rent_assist",      "keywords":["amount","apply","income","deadline"]},
    {"id":"live_gst_credit",    "url":"https://www.canada.ca/en/revenue-agency/services/child-family-benefits/goods-services-tax-harmonized-sales-tax-gst-hst-credit.html",               "topic":"gst_credit",       "keywords":["payment","amount","date","quarterly"]},
    {"id":"live_dental",        "url":"https://www.canada.ca/en/services/benefits/dental/dental-care-plan.html",                                                                           "topic":"dental",           "keywords":["apply","eligible","deadline","coverage"]},
    {"id":"live_mb_hydro",      "url":"https://www.hydro.mb.ca/accounts_and_services/financial_assistance/",                                                                               "topic":"heating",          "keywords":["assistance","apply","income","rebate"]},
    {"id":"live_transit",       "url":"https://winnipegtransit.com/en/fares/reduced-fare-programs",                                                                                        "topic":"transit",          "keywords":["reduced","fare","apply","income"]},
    {"id":"live_min_wage",      "url":"https://www.gov.mb.ca/labour/standards/doc,minimum_wage,factsheet.html",                                                                            "topic":"employment_law",   "keywords":["minimum wage","rate","hour"]},
    {"id":"live_rent_increase", "url":"https://www.gov.mb.ca/housing/rtb/index.html",                                                                                                     "topic":"rent_increase",    "keywords":["rent increase","guideline","percent","notice"]},
    {"id":"live_ei",            "url":"https://www.canada.ca/en/services/benefits/ei/ei-regular-benefit/eligibility.html",                                                                "topic":"ei_rights",        "keywords":["hours","eligibility","rate","weeks"]},
    {"id":"live_ccb",           "url":"https://www.canada.ca/en/revenue-agency/services/child-family-benefits/canada-child-benefit-overview.html",                                        "topic":"ccb",              "keywords":["amount","payment","income","july"]},
    {"id":"live_pharmacare",    "url":"https://www.gov.mb.ca/health/pharmacare/",                                                                                                          "topic":"health",           "keywords":["deductible","income","apply","coverage"]},
]

def scrape_page(url: str, keywords: list) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav","footer","script","style","aside","header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text_lower = text.lower()
        best_pos = 0
        for kw in keywords:
            pos = text_lower.find(kw)
            if pos > 0:
                best_pos = pos
                break
        return text[max(0, best_pos-100): best_pos+2000].strip()
    except Exception as e:
        return f"[scrape error: {e}]"

def content_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def get_stored_hash(page_id: str) -> str:
    try:
        with db_cursor() as (cur, _):
            cur.execute("""
                SELECT content FROM raw_events
                WHERE source='rag_updater' AND title=%s
                ORDER BY scraped_at DESC LIMIT 1
            """, (page_id,))
            row = cur.fetchone()
            return row["content"] if row else ""
    except Exception:
        return ""

def store_hash(page_id: str, hash_val: str, url: str):
    with db_cursor() as (cur, _):
        cur.execute("""
            INSERT INTO raw_events (source, category, title, content, url)
            VALUES ('rag_updater', 'rag_update', %s, %s, %s)
        """, (page_id, hash_val, url))

def groq_summarize_update(page_id: str, new_text: str, topic: str) -> str:
    if not GROQ_API_KEY:
        return new_text[:300]
    prompt = f"""Extract key facts from this government page about {topic} for a Winnipeg Manitoba resident.
Focus on: amounts, dates, deadlines, eligibility, how to apply.
Page content: {new_text[:1500]}
Write 2-3 sentences with specific numbers and dates. Plain text only."""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model": GROQ_MODEL,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": 200, "temperature": 0.1
        }, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return new_text[:300]

def update_rag(page_id: str, topic: str, new_summary: str, url: str):
    collection = get_collection()
    try:
        collection.update(
            ids=[page_id],
            documents=[new_summary],
            metadatas=[{"topic": topic, "updated": datetime.date.today().isoformat()}]
        )
    except Exception:
        collection.add(
            ids=[page_id],
            documents=[new_summary],
            metadatas=[{"topic": topic, "updated": datetime.date.today().isoformat()}]
        )

def run():
    print(f"[RAG Updater] Starting — {datetime.datetime.now()}")
    updated_pages = []
    errors = []

    for page in WATCH_PAGES:
        pid   = page["id"]
        url   = page["url"]
        topic = page["topic"]
        print(f"  checking: {pid}")

        text = scrape_page(url, page["keywords"])
        if text.startswith("[scrape error"):
            errors.append(f"{pid}: {text}")
            continue

        new_hash = content_hash(text[:1000])
        old_hash = get_stored_hash(pid)

        if new_hash == old_hash:
            print(f"    no change")
            continue

        print(f"    CHANGED — updating RAG")
        summary = groq_summarize_update(pid, text, topic)
        update_rag(pid, topic, summary, url)
        store_hash(pid, new_hash, url)
        updated_pages.append(f"*{topic}*: {summary[:100]}...")

    today = datetime.date.today().isoformat()
    if updated_pages:
        msg = f"*🔄 RAG知识库更新 {today}*\n\n"
        msg += "\n\n".join(updated_pages)
        send_message(msg)
        print(f"[RAG Updater] {len(updated_pages)} pages updated")
    else:
        print(f"[RAG Updater] No changes detected")

    if errors:
        print(f"[RAG Updater] {len(errors)} errors: {errors}")

    print(f"[RAG Updater] Done")

if __name__ == "__main__":
    run()
