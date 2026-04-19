#!/usr/bin/env python3
import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.db import db_cursor, insert_raw_event, log_push
from common.telegram_push import send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
HEADERS      = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
FLIPP_URL    = "https://backflipp.wishabi.com/flipp/items/search"

STAPLE_ITEMS = [
    "chicken breast","ground beef","eggs","milk","bread",
    "rice","pasta","canned tomatoes","frozen vegetables","bananas",
    "potatoes","onions","apples","yogurt","butter",
    "cheese","canned beans","oats","cooking oil"
]

def search_flipp(item, postal_code="R3C0A5"):
    try:
        r = requests.get(FLIPP_URL,
            params={"q":item,"locale":"en-CA","postal_code":postal_code},
            headers=HEADERS, timeout=15)
        r.raise_for_status()
        results = []
        for it in r.json().get("items", []):
            price = it.get("current_price", 0)
            if not price or float(price) <= 0:
                continue
            results.append({
                "store": it.get("merchant_name", "Unknown"),
                "item":  item,
                "name":  it.get("name", item),
                "price": float(price),
                "sale":  bool(it.get("sale_story", "")),
            })
        return results
    except Exception as e:
        print(f"  [flipp] {item}: {e}")
        return []

def save_prices(prices):
    with db_cursor() as (cur, _):
        for p in prices:
            cur.execute("""
                INSERT INTO grocery_prices (store, item_name, price, sale)
                VALUES (%s, %s, %s, %s)
            """, (p["store"], p["item"], p["price"], p["sale"]))

def groq_optimize(prices):
    if not GROQ_API_KEY or not prices:
        return "Check Flipp app for this week's deals."
    summary = json.dumps([{"item":p["item"],"store":p["store"],"price":p["price"]} for p in prices[:15]])
    prompt = f"""Winnipeg Manitoba grocery shopping optimization.
This week cheapest prices: {summary}
Write a practical shopping plan: which store first, which store second, estimated weekly total.
One money-saving tip. Plain text, max 100 words."""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model": GROQ_MODEL,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": 200, "temperature": 0.3
        }, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Optimization error: {e}"

def run():
    print(f"[L5] Grocery scanner starting — {datetime.datetime.now()}")
    all_prices = []
    for item in STAPLE_ITEMS:
        results = search_flipp(item)
        if results:
            cheapest = min(results, key=lambda x: x["price"])
            all_prices.append(cheapest)
            print(f"  {item}: ${cheapest['price']:.2f} @ {cheapest['store']}")
        else:
            print(f"  {item}: no results")

    if all_prices:
        save_prices(all_prices)

    route = groq_optimize(all_prices)
    week  = datetime.date.today().strftime("%Y-%m-%d")

    lines = []
    for p in sorted(all_prices, key=lambda x: x["store"]):
        tag = " 🔥" if p["sale"] else ""
        lines.append(f"{p['item']}: ${p['price']:.2f} @ {p['store']}{tag}")

    msg  = f"*🛒 温尼伯本周最低价 {week}*\n\n"
    msg += "\n".join(lines[:20])
    msg += f"\n\n*🗺 采购路线:*\n{route}"
    send_message(msg)
    log_push("telegram", "grocery_digest", lines)
    print(f"[L5] Done — {len(all_prices)} items found")

if __name__ == "__main__":
    run()
