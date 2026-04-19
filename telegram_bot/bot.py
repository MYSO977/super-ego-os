#!/usr/bin/env python3
import os
import sys
import json
import time
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.db import db_cursor, log_push
from common.telegram_push import send_message

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID","")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY","")
BASE_URL         = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

HELP_TEXT = """*🧠 Super-Ego OS 命令*

/decide <内容> → L3冷静层分析
/goal <内容>   → L6微习惯拆解
/benefit       → L4福利状态
/price <商品>  → L5价格查询
/menu          → 本周菜单
/rag <问题>    → 知识库查询
/done <分类>   → 记录习惯完成
/status        → 系统状态
/help          → 本菜单"""

def get_updates(offset=None):
    try:
        r = requests.get(f"{BASE_URL}/getUpdates",
            params={"timeout":30,"offset":offset}, timeout=35)
        r.raise_for_status()
        return r.json().get("result",[])
    except Exception as e:
        print(f"[bot] getUpdates error: {e}")
        return []

def reply(chat_id, text):
    try:
        requests.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id, "text": text,
            "parse_mode": "Markdown", "disable_web_page_preview": True
        }, timeout=10)
    except Exception as e:
        print(f"[bot] reply error: {e}")

def handle_decide(chat_id, text):
    if not text:
        reply(chat_id, "用法: /decide 我想买一台新电脑800元")
        return
    reply(chat_id, f"_🧠 L3分析中..._")
    try:
        from l3_super_ego.cooling_layer_v2 import run as l3_run
        l3_run(text)
    except Exception as e:
        reply(chat_id, f"L3错误: {e}")

def handle_goal(chat_id, text):
    if not text:
        reply(chat_id, "用法: /goal 我想学Python编程")
        return
    reply(chat_id, f"_🌱 拆解目标..._")
    try:
        from l6_happiness.habit_engine import add_goal
        add_goal(text, "learning")
    except Exception as e:
        reply(chat_id, f"L6错误: {e}")

def handle_benefit(chat_id):
    try:
        with db_cursor() as (cur,_):
            cur.execute("""
                SELECT re.title, es.urgency_score, es.summary, es.deadline
                FROM ego_signals es JOIN raw_events re ON es.raw_event_id=re.id
                WHERE es.signal_type='benefit'
                ORDER BY es.created_at DESC LIMIT 6
            """)
            rows = cur.fetchall()
        if not rows:
            reply(chat_id, "暂无福利数据，等待明日07:30扫描")
            return
        lines = ["*💊 曼省福利状态*",""]
        for row in rows:
            u = float(row["urgency_score"] or 0)
            e = "🔴" if u>=7 else "🟡" if u>=4 else "🟢"
            lines.append(f"{e} *{row['title']}* [{u:.0f}/10]")
            if row["summary"]: lines.append(f"  {row['summary'][:80]}")
            if row["deadline"]: lines.append(f"  ⏰ {row['deadline']}")
        reply(chat_id, "\n".join(lines))
    except Exception as e:
        reply(chat_id, f"查询失败: {e}")

def handle_price(chat_id, item):
    if not item:
        reply(chat_id, "用法: /price eggs")
        return
    try:
        with db_cursor() as (cur,_):
            cur.execute("""
                SELECT item_name, price, store FROM grocery_prices
                WHERE item_name ILIKE %s AND scraped_at > NOW() - INTERVAL '7 days'
                ORDER BY price ASC LIMIT 5
            """, (f"%{item}%",))
            rows = cur.fetchall()
        if not rows:
            reply(chat_id, f"未找到 '{item}' 价格，等待周日08:00扫描")
            return
        lines = [f"*🛒 {item} 本周价格*",""]
        for r in rows:
            lines.append(f"• ${r['price']:.2f} @ {r['store']}")
        reply(chat_id, "\n".join(lines))
    except Exception as e:
        reply(chat_id, f"查询失败: {e}")

def handle_rag(chat_id, question):
    if not question:
        reply(chat_id, "用法: /rag 租户被驱逐怎么办")
        return
    try:
        from rag.rag_query import get_context
        context = get_context(question, n=3)
        if not context:
            reply(chat_id, "知识库无相关内容")
            return
        if GROQ_API_KEY:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"},
                json={"model":"llama-3.1-8b-instant",
                      "messages":[{"role":"user","content":f"Answer in Chinese, specific and practical.\nQ: {question}\nContext: {context}"}],
                      "max_tokens":300,"temperature":0.2}, timeout=20)
            answer = r.json()["choices"][0]["message"]["content"].strip()
        else:
            answer = context
        reply(chat_id, f"*🧠 知识库*\n\n{answer}")
    except Exception as e:
        reply(chat_id, f"查询失败: {e}")

def handle_done(chat_id, category):
    cat = category.strip() if category else "general"
    try:
        with db_cursor() as (cur,_):
            cur.execute("""
                UPDATE happiness_tasks SET completed=TRUE
                WHERE id=(SELECT id FROM happiness_tasks
                    WHERE category=%s AND completed=FALSE
                    AND created_at > NOW() - INTERVAL '1 day'
                    ORDER BY created_at DESC LIMIT 1)
            """, (cat,))
        reply(chat_id, f"✅ 记录完成: {cat}\n_继续保持！_")
    except Exception as e:
        reply(chat_id, f"记录失败: {e}")

def handle_status(chat_id):
    try:
        with db_cursor() as (cur,_):
            cur.execute("SELECT COUNT(*) as n FROM raw_events WHERE scraped_at > NOW() - INTERVAL '24 hours'")
            e24 = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) as n FROM push_log WHERE sent_at > NOW() - INTERVAL '24 hours' AND success=TRUE")
            p24 = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) as n FROM ego_decisions")
            dec = cur.fetchone()["n"]
        from rag.knowledge_base import get_collection
        rag = len(get_collection().get()["ids"])
        now = datetime.datetime.now().strftime("%m-%d %H:%M")
        reply(chat_id, f"*⚙️ 系统状态 {now}*\n\n📥 24h事件: {e24}\n📤 24h推送: {p24}\n🧠 决策记录: {dec}\n📚 RAG知识: {rag}条")
    except Exception as e:
        reply(chat_id, f"状态查询失败: {e}")

def route(chat_id, text):
    text = text.strip()
    if not text.startswith("/"):
        if len(text) > 10:
            reply(chat_id, "_自动路由到L3分析..._")
            handle_decide(chat_id, text)
        return
    parts = text.split(" ",1)
    cmd   = parts[0].lower().split("@")[0]
    args  = parts[1] if len(parts)>1 else ""
    if   cmd=="/decide":  handle_decide(chat_id, args)
    elif cmd=="/goal":    handle_goal(chat_id, args)
    elif cmd=="/benefit": handle_benefit(chat_id)
    elif cmd=="/price":   handle_price(chat_id, args)
    elif cmd=="/menu":    handle_menu(chat_id)
    elif cmd=="/rag":     handle_rag(chat_id, args)
    elif cmd=="/done":    handle_done(chat_id, args)
    elif cmd=="/status":  handle_status(chat_id)
    elif cmd=="/transit": handle_transit(chat_id, args)
    elif cmd in ("/help","/start"): reply(chat_id, HELP_TEXT)
    else: reply(chat_id, f"未知命令: {cmd}\n/help 查看列表")

def handle_transit(chat_id, text):
    if not text:
        reply(chat_id, "用法: /transit 市中心 到 大学")
        return
    parts = text.split(" 到 ", 1) if " 到 " in text else text.split(" to ", 1)
    if len(parts) != 2:
        reply(chat_id, "用法: /transit 出发地 到 目的地")
        return
    origin, dest = parts[0].strip(), parts[1].strip()
    reply(chat_id, f"_🚌 规划路线: {origin} → {dest}..._")
    try:
        from l5_life_os.transit_optimizer import groq_plan_route, format_route
        route = groq_plan_route(origin, dest)
        reply(chat_id, format_route(origin, dest, route))
    except Exception as e:
        reply(chat_id, f"路线规划失败: {e}")

def handle_menu(chat_id):
    reply(chat_id, "_🍽 生成菜单..._")
    try:
        from l5_life_os.meal_planner import run as meal_run
        meal_run()
    except Exception as e:
        reply(chat_id, f"菜单失败: {e}")

def run():
    print(f"[Bot] Starting — {datetime.datetime.now()}")
    offset = None
    reply(TELEGRAM_CHAT_ID, "🤖 *Super-Ego OS Bot 已启动*\n/help 查看命令")
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"]+1
                msg = update.get("message") or update.get("edited_message")
                if not msg: continue
                chat_id = str(msg["chat"]["id"])
                if chat_id != str(TELEGRAM_CHAT_ID):
                    reply(chat_id, "⛔ 未授权")
                    continue
                text = msg.get("text","")
                if text:
                    print(f"[bot] {text[:50]}")
                    route(chat_id, text)
        except KeyboardInterrupt:
            print("[Bot] Stopped")
            break
        except Exception as e:
            print(f"[bot] error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
