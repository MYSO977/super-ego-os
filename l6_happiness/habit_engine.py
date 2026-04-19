#!/usr/bin/env python3
import os
import sys
import json
import datetime
import argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.db import db_cursor, log_push
from common.telegram_push import send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_GOALS = [
    {"id":"g001","category":"health",  "goal":"保持身体健康"},
    {"id":"g002","category":"finance", "goal":"改善财务状况"},
    {"id":"g003","category":"social",  "goal":"维持社交连接防止孤独"},
    {"id":"g004","category":"learning","goal":"持续学习新技能"},
    {"id":"g005","category":"exercise","goal":"每天保持运动"},
    {"id":"g006","category":"mental",  "goal":"保持心理健康"},
    {"id":"g007","category":"home",    "goal":"维持居家整洁"},
    {"id":"g008","category":"career",  "goal":"提升职业技能"},
]

CATEGORY_EMOJI = {
    "health":"💊","finance":"💰","social":"👥","learning":"📚",
    "exercise":"🏃","mental":"🧘","home":"🏠","career":"💼"
}

def groq_decompose(goal, category, difficulty_level=1):
    time_map = {1:"2 minutes",2:"5 minutes",3:"10 minutes"}
    time_str = time_map.get(difficulty_level,"5 minutes")
    prompt = f"""Behavioral psychology expert helping build habits through tiny actions.
Goal: {goal} | Category: {category} | Max time: {time_str} | Location: Winnipeg Manitoba, limited budget
Generate exactly 3 micro-tasks SO EASY they cannot be refused.
Each: max {time_str}, zero cost, specific and actionable.
Respond ONLY with JSON array (no markdown):
[{{"task":"exact action","time_minutes":2,"trigger":"when/where","why":"one sentence"}}]"""
    try:
        headers = {"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model":GROQ_MODEL,
            "messages":[{"role":"user","content":prompt}],
            "max_tokens":400,"temperature":0.4
        }, timeout=20)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  [groq] {e}")
        return [
            {"task":f"花2分钟写下{goal}的一个小步骤","time_minutes":2,"trigger":"早上醒来","why":"启动比完成更重要"},
            {"task":"做一个与目标相关的最小动作","time_minutes":2,"trigger":"午饭后","why":"积累胜于爆发"},
            {"task":"睡前回顾今天做了什么","time_minutes":1,"trigger":"睡前","why":"记录建立动力"},
        ]

def get_completion_rate(category, days=7):
    try:
        with db_cursor() as (cur,_):
            cur.execute("""
                SELECT COUNT(*) as total, SUM(CASE WHEN completed THEN 1 ELSE 0 END) as done
                FROM happiness_tasks WHERE category=%s AND created_at > NOW() - INTERVAL '7 days'
            """, (category,))
            row = cur.fetchone()
            return float(row["done"] or 0)/float(row["total"]) if row["total"] else 0.5
    except Exception:
        return 0.5

def get_difficulty(rate):
    if rate < 0.3: return 1
    elif rate < 0.6: return 2
    else: return 3

def save_tasks(tasks, category, week_start):
    with db_cursor() as (cur,_):
        for t in tasks:
            cur.execute("""
                INSERT INTO happiness_tasks (week_start, category, task)
                VALUES (%s,%s,%s)
            """, (week_start, category, json.dumps(t)))

def daily_push():
    today      = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    dow        = today.weekday()
    goals_today = DEFAULT_GOALS[dow % len(DEFAULT_GOALS): dow % len(DEFAULT_GOALS)+2]
    lines = [f"*🌱 今日微习惯 {today.strftime('%m-%d %a')}*",""]
    for g in goals_today:
        cat   = g["category"]
        emoji = CATEGORY_EMOJI.get(cat,"✨")
        rate  = get_completion_rate(cat)
        diff  = get_difficulty(rate)
        tasks = groq_decompose(g["goal"], cat, diff)
        save_tasks(tasks, cat, week_start)
        lines.append(f"{emoji} *{g['goal']}*")
        for t in tasks[:2]:
            lines.append(f"  • {t['task']} _({t.get('time_minutes',2)}min — {t.get('trigger','')})_")
        lines.append("")
    lines.append("_完成后回复 /done 记录_")
    send_message("\n".join(lines))
    log_push("telegram","daily_habits",lines)
    print(f"[L6] Daily habits pushed")

def weekly_report():
    lines = [f"*📊 本周习惯报告 {datetime.date.today()}*",""]
    for g in DEFAULT_GOALS:
        cat  = g["category"]
        rate = get_completion_rate(cat)
        bar  = "█"*int(rate*10) + "░"*(10-int(rate*10))
        lines.append(f"{CATEGORY_EMOJI.get(cat,'✨')} {g['goal']}: {bar} {int(rate*100)}%")
    send_message("\n".join(lines))
    log_push("telegram","weekly_habit_report",lines)
    print("[L6] Weekly report pushed")

def add_goal(goal_text, category="learning"):
    tasks = groq_decompose(goal_text, category, 1)
    today = datetime.date.today()
    save_tasks(tasks, category, today - datetime.timedelta(days=today.weekday()))
    emoji = CATEGORY_EMOJI.get(category,"✨")
    lines = [f"*{emoji} 新目标微习惯*", f"*目标:* {goal_text}",""]
    for t in tasks:
        lines.append(f"• {t['task']} _({t.get('time_minutes',2)}min)_")
        lines.append(f"  _{t.get('why','')}_")
    send_message("\n".join(lines))
    print(f"[L6] {len(tasks)} micro-tasks generated")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily",    action="store_true")
    parser.add_argument("--weekly",   action="store_true")
    parser.add_argument("--goal",     type=str)
    parser.add_argument("--category", type=str, default="learning")
    args = parser.parse_args()
    if args.daily:   daily_push()
    elif args.weekly: weekly_report()
    elif args.goal:  add_goal(args.goal, args.category)
    else:            daily_push()
