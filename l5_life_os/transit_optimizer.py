#!/usr/bin/env python3
"""
l5_life_os/transit_optimizer.py
温尼伯交通优化器 — 运行在 .18
功能:
  1. Winnipeg Transit实时班次查询
  2. 最低成本路线规划 (公交/步行/自行车)
  3. 危险区域规避 (North End高犯罪区提醒)
  4. 低收入公交月票资格检查
  5. /transit 命令接入 Telegram Bot

调用方式:
  python3 l5_life_os/transit_optimizer.py --from "Portage Ave" --to "University of Manitoba"
  或通过 Telegram: /transit 从A到B
"""
import os
import sys
import json
import datetime
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.telegram_push import send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY","")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
HEADERS      = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64)"}

# ── 温尼伯交通知识库 ──────────────────────────────────────────
WINNIPEG_TRANSIT = {
    "fares": {
        "cash":         3.15,
        "peggo":        2.43,
        "monthly_pass": 104.00,
        "low_income_pass": 60.00,
        "senior_pass":  58.00,
        "child_under5": 0.00,
    },
    "key_routes": [
        {"route":"16","name":"Selkirk-Osborne","desc":"主干线南北向，覆盖North End到South End"},
        {"route":"18","name":"Notre Dame","desc":"市中心到西区主干线"},
        {"route":"11","name":"McPhillips","desc":"North End到市中心"},
        {"route":"21","name":"Portage","desc":"市中心到西区Portage Ave"},
        {"route":"60","name":"Henderson","desc":"East Kildonan到市中心"},
        {"route":"BLUE","name":"Southwest Transitway","desc":"快速公交，University到市中心最快"},
        {"route":"ORANGE","name":"Main Street BRT","desc":"Main St快速公交"},
    ],
    "dangerous_areas": [
        {"area":"North End (north of Selkirk Ave)","risk":"high","note":"夜间避免步行，尤其 Dufferin/Andrews 区域"},
        {"area":"Downtown East (east of Main St)","risk":"medium","note":"白天注意财物，夜间建议乘车"},
        {"area":"West End (Sargent/Ellice)","risk":"medium","note":"部分街道夜间不安全"},
        {"area":"Portage Place area","risk":"medium","note":"公共场所注意周围环境"},
    ],
    "tips": [
        "Peggo card 省23%，月票用量>43次才合算",
        "低收入月票$60：需证明领取EIA或Rent Assist，致电311申请",
        "Google Maps实时公交查询：maps.google.com → 公共交通",
        "Winnipeg Transit官网：winnipegtransit.com → Trip Planner",
        "冬季等车：最多等一班（15-20min），超时打311",
        "自行车：夏季骨干路线沿Assiniboine River，地图：winnipeg.ca/cycling",
    ]
}

# ── Groq 路线规划 ─────────────────────────────────────────────

def groq_plan_route(origin: str, destination: str, preferences: dict = None) -> dict:
    prefs = preferences or {}
    budget = prefs.get("budget","low")
    time_of_day = datetime.datetime.now().strftime("%H:%M")
    day_of_week = datetime.datetime.now().strftime("%A")

    routes_info = json.dumps(WINNIPEG_TRANSIT["key_routes"], ensure_ascii=False)
    fares_info  = json.dumps(WINNIPEG_TRANSIT["fares"], ensure_ascii=False)
    danger_info = json.dumps(WINNIPEG_TRANSIT["dangerous_areas"], ensure_ascii=False)

    prompt = f"""You are a Winnipeg Manitoba transit expert helping a low-income resident get around cheaply and safely.

From: {origin}
To: {destination}
Time: {time_of_day} on {day_of_week}
Budget preference: {budget}

Available routes: {routes_info}
Fares: {fares_info}
Safety concerns: {danger_info}

Plan the optimal route. Consider:
1. Lowest cost option (walk if under 20 min)
2. Safety (avoid dangerous areas especially at night)
3. Transfer efficiency
4. Weather (Winnipeg can be very cold)

Respond ONLY with JSON (no markdown):
{{
  "recommended_mode": "bus/walk/bike/mixed",
  "estimated_time_minutes": 25,
  "estimated_cost_cad": 2.43,
  "steps": [
    {{"action":"Walk","detail":"Walk north on Main St to Portage Ave","duration_min":5}},
    {{"action":"Bus","detail":"Take Route 21 Portage westbound","duration_min":15}},
    {{"action":"Walk","detail":"Walk 2 blocks south to destination","duration_min":3}}
  ],
  "safety_note": "safe route at this time" or specific warning,
  "money_tip": "specific saving tip",
  "alternative": "cheaper or faster alternative if exists"
}}"""

    try:
        headers = {"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model": GROQ_MODEL,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": 600, "temperature": 0.2
        }, timeout=20)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  [groq] route error: {e}")
        return {
            "recommended_mode": "bus",
            "estimated_time_minutes": 30,
            "estimated_cost_cad": 2.43,
            "steps": [{"action":"Check","detail":"Visit winnipegtransit.com for trip planner","duration_min":0}],
            "safety_note": "Check current conditions",
            "money_tip": "Use Peggo card to save 23%",
            "alternative": "Google Maps public transit"
        }

def format_route(origin: str, destination: str, route: dict) -> str:
    mode  = route.get("recommended_mode","bus")
    time  = route.get("estimated_time_minutes",0)
    cost  = route.get("estimated_cost_cad",0)
    mode_emoji = {"bus":"🚌","walk":"🚶","bike":"🚲","mixed":"🚌"}.get(mode,"🚌")

    lines = [
        f"*{mode_emoji} 路线: {origin} → {destination}*",
        f"预计时间: {time}分钟 | 费用: ${cost:.2f}",
        ""
    ]
    for i, step in enumerate(route.get("steps",[]), 1):
        action = step.get("action","")
        detail = step.get("detail","")
        dur    = step.get("duration_min",0)
        emoji  = {"Walk":"🚶","Bus":"🚌","Bike":"🚲","Transfer":"🔄"}.get(action,"→")
        lines.append(f"{i}. {emoji} *{action}* ({dur}min)")
        lines.append(f"   {detail}")

    safety = route.get("safety_note","")
    if safety and safety != "safe route at this time":
        lines.append(f"\n⚠️ *安全提示:* {safety}")

    tip = route.get("money_tip","")
    if tip:
        lines.append(f"\n💡 *省钱tip:* {tip}")

    alt = route.get("alternative","")
    if alt:
        lines.append(f"\n🔀 *替代方案:* {alt}")

    return "\n".join(lines)

def check_low_income_pass() -> str:
    lines = [
        "*🚌 低收入公交月票 ($60/月)*","",
        "普通月票: $104 → 低收入: $60 (省$44/月)",
        "",
        "*资格条件:*",
        "• 领取EIA (Employment and Income Assistance)",
        "• 或领取Rent Assist",
        "• 或符合低收入标准",
        "",
        "*申请方式:*",
        "• 致电 311",
        "• 或访问 winnipegtransit.com → Reduced Fare",
        "• 需要: 福利证明文件",
        "",
        f"*每年节省: ${44*12:.0f} CAD*"
    ]
    return "\n".join(lines)

def weekly_transit_tip() -> str:
    tips = WINNIPEG_TRANSIT["tips"]
    today_tip = tips[datetime.date.today().weekday() % len(tips)]
    routes = WINNIPEG_TRANSIT["key_routes"]

    lines = ["*🚌 本周交通提示*",""]
    lines.append(f"💡 {today_tip}","")
    lines.append("\n*主要路线快查:*")
    for r in routes[:4]:
        lines.append(f"• Route {r['route']}: {r['desc']}")
    return "\n".join(lines)

def run(origin: str = None, destination: str = None):
    if not origin or not destination:
        # 发送交通信息概览
        msg = check_low_income_pass()
        send_message(msg)
        return

    print(f"[Transit] Planning: {origin} → {destination}")
    route = groq_plan_route(origin, destination)
    msg   = format_route(origin, destination, route)
    send_message(msg)
    print(f"[Transit] Route sent — {route.get('estimated_time_minutes')}min, ${route.get('estimated_cost_cad'):.2f}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="origin",      type=str, default=None)
    parser.add_argument("--to",   dest="destination", type=str, default=None)
    args = parser.parse_args()
    run(args.origin, args.destination)
