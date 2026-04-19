#!/usr/bin/env python3
import os
import sys
import json
import datetime
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.db import db_cursor, insert_raw_event, log_push
from common.telegram_push import send_digest, send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
HEADERS      = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

BENEFITS = [
    {"name": "CAIP Carbon Rebate",      "url": "https://www.canada.ca/en/revenue-agency/services/child-family-benefits/canada-carbon-rebate.html",                                                   "keywords": ["payment date","amount","quarterly"]},
    {"name": "Rent Assist",             "url": "https://www.gov.mb.ca/housing/assist/",                                                                                                              "keywords": ["application","deadline","income","amount"]},
    {"name": "GST/HST Credit",          "url": "https://www.canada.ca/en/revenue-agency/services/child-family-benefits/goods-services-tax-harmonized-sales-tax-gst-hst-credit.html",               "keywords": ["payment date","quarterly","income"]},
    {"name": "MB Hydro Low Income",     "url": "https://www.hydro.mb.ca/accounts_and_services/financial_assistance/",                                                                               "keywords": ["apply","low income","rebate","discount"]},
    {"name": "MB Transit Pass Subsidy", "url": "https://winnipegtransit.com/en/fares/reduced-fare-programs",                                                                                        "keywords": ["reduced fare","apply","income"]},
    {"name": "Canada Dental Benefit",   "url": "https://www.canada.ca/en/services/benefits/dental/dental-care-plan.html",                                                                           "keywords": ["enroll","eligible","income","apply"]},
]

def scrape_benefit(benefit):
    try:
        url = benefit["url"]
        if url.endswith(".pdf"):
            return f"[PDF — manual check: {url}]"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav","footer","script","style","aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        best_pos = 0
        for kw in benefit["keywords"]:
            pos = text.lower().find(kw)
            if pos > 0:
                best_pos = pos
                break
        return text[max(0, best_pos-200): best_pos+1800].strip()
    except Exception as e:
        return f"[scrape error: {e}]"

def groq_score(benefit_name, page_text):
    if not GROQ_API_KEY:
        return {"urgency":5,"summary":"Groq key not set","action":"Check manually","deadline":None,"amount_monthly_cad":0}
    prompt = f"""You are a Canadian benefits advisor for a Winnipeg Manitoba resident.
Benefit: {benefit_name}
Page snippet: {page_text[:1500]}
Today: {datetime.date.today().isoformat()}
Respond ONLY with JSON (no markdown):
{{"urgency":8,"summary":"one sentence","action":"specific action or no action needed","deadline":"YYYY-MM-DD or null","amount_monthly_cad":100}}
urgency 0-10 (10=act today)"""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model": GROQ_MODEL,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": 200, "temperature": 0.1
        }, timeout=20)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        return {"urgency":5,"summary":str(e),"action":"Manual check","deadline":None,"amount_monthly_cad":0}

def write_signal(benefit_name, result, raw_event_id):
    deadline = None
    if result.get("deadline"):
        try:
            deadline = datetime.date.fromisoformat(result["deadline"])
        except Exception:
            pass
    with db_cursor() as (cur, _):
        cur.execute("""
            INSERT INTO ego_signals (raw_event_id, signal_type, urgency_score, summary, action_required, deadline)
            VALUES (%s, 'benefit', %s, %s, %s, %s)
        """, (raw_event_id, result.get("urgency",5), result.get("summary",""), result.get("action",""), deadline))

def update_benefit(benefit_name, result):
    with db_cursor() as (cur, _):
        cur.execute("""
            UPDATE mb_benefits SET last_checked=NOW(), notes=%s, apply_steps=%s, deadline=%s, updated_at=NOW()
            WHERE benefit_name=%s
        """, (result.get("summary",""), result.get("action",""), result.get("deadline"), benefit_name))

def run():
    print(f"[L4] Starting — {datetime.datetime.now()}")
    digest_items = []
    urgent_items = []
    for benefit in BENEFITS:
        name = benefit["name"]
        print(f"  checking: {name}")
        page_text = scrape_benefit(benefit)
        raw_id = insert_raw_event("benefit_scraper","manitoba_benefit", name, page_text[:4000], benefit["url"])
        result = groq_score(name, page_text)
        write_signal(name, result, raw_id)
        update_benefit(name, result)
        urgency = result.get("urgency",0)
        amt     = result.get("amount_monthly_cad",0)
        line = f"*{name}* [{urgency}/10]"
        if amt:
            line += f" ~${amt}/mo"
        line += f"\n  {result.get('summary','')}"
        if result.get("action","") not in ("","no action needed"):
            line += f"\n  → {result.get('action')}"
        if result.get("deadline"):
            line += f"\n  ⏰ {result.get('deadline')}"
        digest_items.append(line)
        if urgency >= 7:
            urgent_items.append(line)
        print(f"    urgency={urgency}")
    today = datetime.date.today().strftime("%Y-%m-%d %a")
    send_digest(f"曼省福利日报 {today}", digest_items)
    log_push("telegram","benefit_digest", digest_items)
    if urgent_items:
        send_message("*⚠️ 紧急福利提醒*\n\n" + "\n\n".join(urgent_items))
    print(f"[L4] Done — {len(BENEFITS)} benefits checked")

if __name__ == "__main__":
    run()
