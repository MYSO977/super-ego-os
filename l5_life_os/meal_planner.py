#!/usr/bin/env python3
"""
l5_life_os/meal_planner.py
每周最低成本菜单生成器 — 运行在 .18
每周日 08:30 在 grocery_scanner 之后运行
基于本周实际最低价生成7天菜单+购物清单+采购路线

Cron (.18): 30 8 * * 0 python3 /home/heng/super-ego-os/l5_life_os/meal_planner.py
"""
import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.db import db_cursor, log_push
from common.telegram_push import send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

WINNIPEG_CONTEXT = """
Location: Winnipeg Manitoba Canada
Climate: Cold (need warming foods in winter/fall/spring)
Budget: Extremely low, maximize nutrition per dollar
Cooking: Basic equipment assumed (stove, pot, pan)
Dietary: No restrictions unless specified
"""

def get_this_week_prices() -> list[dict]:
    """从DB获取本周grocery_scanner抓到的最低价"""
    try:
        with db_cursor() as (cur, _):
            cur.execute("""
                SELECT item_name, MIN(price) as price, store
                FROM grocery_prices
                WHERE scraped_at > NOW() - INTERVAL '7 days'
                GROUP BY item_name, store
                ORDER BY price ASC
            """)
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []
    except Exception as e:
        print(f"  [db] price fetch error: {e}")
        return []

def get_fallback_prices() -> list[dict]:
    """如果DB没有数据，用默认温尼伯价格"""
    return [
        {"item_name":"eggs",              "price":4.99,  "store":"No Frills"},
        {"item_name":"chicken breast",    "price":7.99,  "store":"Superstore"},
        {"item_name":"ground beef",       "price":5.99,  "store":"Walmart"},
        {"item_name":"canned beans",      "price":1.29,  "store":"No Frills"},
        {"item_name":"rice (2kg)",        "price":4.99,  "store":"No Frills"},
        {"item_name":"pasta",             "price":1.99,  "store":"Walmart"},
        {"item_name":"bread",             "price":2.99,  "store":"No Frills"},
        {"item_name":"milk (2L)",         "price":3.99,  "store":"Superstore"},
        {"item_name":"canned tomatoes",   "price":1.49,  "store":"No Frills"},
        {"item_name":"frozen vegetables", "price":2.99,  "store":"Walmart"},
        {"item_name":"bananas",           "price":1.49,  "store":"Superstore"},
        {"item_name":"potatoes (5lb)",    "price":3.99,  "store":"No Frills"},
        {"item_name":"onions",            "price":1.99,  "store":"Walmart"},
        {"item_name":"oats",              "price":3.49,  "store":"Walmart"},
        {"item_name":"butter",            "price":4.99,  "store":"Superstore"},
        {"item_name":"cooking oil",       "price":5.99,  "store":"Walmart"},
        {"item_name":"canned tuna",       "price":1.99,  "store":"No Frills"},
        {"item_name":"lentils",           "price":2.49,  "store":"No Frills"},
        {"item_name":"carrots",           "price":1.99,  "store":"Walmart"},
        {"item_name":"apples",            "price":3.99,  "store":"Superstore"},
    ]

def groq_generate_menu(prices: list[dict]) -> dict:
    price_summary = "\n".join([f"- {p['item_name']}: ${p['price']:.2f} @ {p['store']}" for p in prices[:20]])
    prompt = f"""You are a budget meal planning expert for Winnipeg Manitoba Canada.

Available ingredients this week (cheapest prices found):
{price_summary}

{WINNIPEG_CONTEXT}

Create a 7-day meal plan that:
1. Minimizes total weekly cost (target under $60 CAD for one person)
2. Maximizes nutrition (protein, vegetables, variety)
3. Uses batch cooking (cook once, eat twice)
4. Includes simple recipes (under 30 min prep)

Respond ONLY with JSON (no markdown):
{{
  "weekly_budget": 55.00,
  "days": [
    {{
      "day": "Monday",
      "breakfast": {{"meal":"Oatmeal with banana","cost":0.80,"time_min":5}},
      "lunch":     {{"meal":"Rice and beans","cost":1.20,"time_min":10}},
      "dinner":    {{"meal":"Chicken stir-fry with frozen vegetables","cost":3.50,"time_min":20}}
    }}
  ],
  "batch_cook_tips": ["Cook rice in bulk Sunday", "Marinate chicken overnight"],
  "shopping_list": [
    {{"item":"eggs","quantity":"12","estimated_cost":4.99,"store":"No Frills"}},
    {{"item":"rice","quantity":"2kg","estimated_cost":4.99,"store":"No Frills"}}
  ],
  "store_route": [
    {{"store":"No Frills","items":["eggs","rice","beans"],"subtotal":8.27}},
    {{"store":"Walmart","items":["frozen vegetables","pasta"],"subtotal":4.98}}
  ],
  "money_tip": "One specific money-saving tip for this week"
}}"""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model": GROQ_MODEL,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": 1500, "temperature": 0.3
        }, timeout=30)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  [groq] menu error: {e}")
        return {}

def format_menu_message(menu: dict) -> list[str]:
    """拆成多条消息，避免Telegram 4096字符限制"""
    messages = []
    week = datetime.date.today().strftime("%Y-%m-%d")
    budget = menu.get("weekly_budget", 0)

    # 消息1：菜单概览
    msg1 = [f"*🍽 本周菜单 {week}*", f"*预算目标: ${budget:.2f}/周*", ""]
    for day_data in menu.get("days", [])[:7]:
        day = day_data.get("day","")
        b   = day_data.get("breakfast",{})
        l   = day_data.get("lunch",{})
        d   = day_data.get("dinner",{})
        day_cost = sum([b.get("cost",0), l.get("cost",0), d.get("cost",0)])
        msg1.append(f"*{day}* (${day_cost:.2f})")
        msg1.append(f"  早: {b.get('meal','')} ({b.get('time_min',0)}min)")
        msg1.append(f"  午: {l.get('meal','')} ({l.get('time_min',0)}min)")
        msg1.append(f"  晚: {d.get('meal','')} ({d.get('time_min',0)}min)")
    messages.append("\n".join(msg1))

    # 消息2：购物清单
    msg2 = ["*🛒 本周购物清单*", ""]
    shopping = menu.get("shopping_list", [])
    total = 0
    for item in shopping:
        cost = item.get("estimated_cost", 0)
        total += cost
        msg2.append(f"• {item['item']} {item.get('quantity','')} — ${cost:.2f} @ {item.get('store','')}")
    msg2.append(f"\n*合计: ${total:.2f}*")
    messages.append("\n".join(msg2))

    # 消息3：采购路线
    msg3 = ["*🗺 最优采购路线*", ""]
    for stop in menu.get("store_route", []):
        store    = stop.get("store","")
        items    = ", ".join(stop.get("items",[]))
        subtotal = stop.get("subtotal",0)
        msg3.append(f"*{store}* (${subtotal:.2f})")
        msg3.append(f"  买: {items}")
    tips = menu.get("batch_cook_tips", [])
    if tips:
        msg3.append("\n*批量烹饪技巧:*")
        for tip in tips:
            msg3.append(f"  • {tip}")
    tip = menu.get("money_tip","")
    if tip:
        msg3.append(f"\n*💡 本周省钱tip:* _{tip}_")
    messages.append("\n".join(msg3))

    return messages

def run():
    print(f"[L5 Meal] Starting — {datetime.datetime.now()}")
    prices = get_this_week_prices()
    if not prices:
        print("  No DB prices found, using fallback")
        prices = get_fallback_prices()
    else:
        print(f"  Using {len(prices)} prices from DB")

    menu = groq_generate_menu(prices)
    if not menu:
        send_message("*🍽 菜单生成失败* — 请手动检查")
        return

    messages = format_menu_message(menu)
    for msg in messages:
        send_message(msg)

    log_push("telegram", "weekly_menu", {"budget": menu.get("weekly_budget")})
    print(f"[L5 Meal] Done — {len(messages)} messages sent")

if __name__ == "__main__":
    run()
