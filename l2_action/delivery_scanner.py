#!/usr/bin/env python3
import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from common.db import db_cursor, log_push
from common.telegram_push import send_message

GROQ_API_KEY = os.getenv("GROQ_API_KEY","")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

PLATFORMS = [
    {"name":"SkipTheDishes", "type":"送餐",   "emoji":"🍔","hourly":18,"signup":"https://www.skipthedishes.com/driver",        "vehicle":["bicycle","car"],     "peak":["11:30-14:00","17:00-21:00","周末全天"],   "pay":"基础$4-7+小费+距离",    "payout":"每周四",   "signup_time":"10分钟",  "pros":["无需经验","自选时间","即时提现"],         "cons":["冬季骑车危险","停车费自付"]},
    {"name":"DoorDash",      "type":"送餐",   "emoji":"🚗","hourly":17,"signup":"https://dasher.doordash.com/en-ca",           "vehicle":["bicycle","car"],     "peak":["12:00-14:00","18:00-22:00","周末"],       "pay":"$2-10+小费+Peak Pay",  "payout":"即时提现", "signup_time":"15分钟",  "pros":["DashDirect即时","Peak高峰奖励"],         "cons":["背景调查3-7天"]},
    {"name":"Uber Eats",     "type":"送餐",   "emoji":"🛵","hourly":16,"signup":"https://www.uber.com/ca/en/deliver/",         "vehicle":["bicycle","car"],     "peak":["11:00-14:00","17:30-21:30","恶劣天气"],   "pay":"基础+$0.80/km+小费",   "payout":"随时提现", "signup_time":"20分钟",  "pros":["随时提现","恶劣天气奖励"],               "cons":["需车险证明"]},
    {"name":"Amazon Flex",   "type":"送快递", "emoji":"📦","hourly":22,"signup":"https://flex.amazon.ca",                      "vehicle":["car","suv"],         "peak":["07:00-12:00","12:00-17:00"],              "pay":"$18-25/hr固定班次",    "payout":"每周二",   "signup_time":"审核1-2周","pros":["时薪最高","固定班次好规划"],             "cons":["需要大车","app抢班次"]},
    {"name":"Instacart",     "type":"买菜配送","emoji":"🛒","hourly":20,"signup":"https://shoppers.instacart.ca",              "vehicle":["car"],               "peak":["09:00-12:00","15:00-19:00","周末全天"],   "pay":"$7-15/单+小费$5-8",    "payout":"每周三",   "signup_time":"15分钟",  "pros":["小费高","快速审批"],                     "cons":["需垫付购物款"]},
    {"name":"Purolator临时", "type":"送快递", "emoji":"🚚","hourly":19,"signup":"https://ca.indeed.com/jobs?q=courier+driver&l=Winnipeg","vehicle":["car","van"],"peak":["周一至周五白天"],                    "pay":"$16-22/hr按件计费",    "payout":"双周薪",   "signup_time":"投简历1-3天","pros":["稳定收入","节假日大量机会"],            "cons":["时间不灵活","体力工作"]},
    {"name":"Kijiji零工",    "type":"本地零工","emoji":"🔧","hourly":20,"signup":"https://www.kijiji.ca/b-part-time-jobs/winnipeg/k0c45l1700192","vehicle":["any"],"peak":["随时"],                            "pay":"$15-30/hr协商",        "payout":"当天现金", "signup_time":"发帖即可", "pros":["现金即付","无需平台","灵活"],            "cons":["需要自己找客户"]},
    {"name":"TaskRabbit",    "type":"本地零工","emoji":"🪛","hourly":25,"signup":"https://www.taskrabbit.ca",                  "vehicle":["any"],               "peak":["周末","月初月末(搬家季)"],                "pay":"$20-40/hr自定价",      "payout":"完成后1天","signup_time":"30分钟",  "pros":["定价自由","搬家/组装高需求"],            "cons":["需要建立评价"]},
]

def calc_income(p, hrs_day=3, days_week=5):
    gross_w = p["hourly"] * hrs_day * days_week
    gross_m = round(gross_w * 4.33)
    fuel    = round(20 * 0.12 * hrs_day * days_week * 4.33) if "car" in p["vehicle"] else 0
    return {"weekly": round(gross_w), "monthly": gross_m, "fuel": fuel, "net": gross_m - fuel}

def groq_strategy():
    if not GROQ_API_KEY:
        return {"combo":["SkipTheDishes","Amazon Flex"],"schedule":{"Mon-Fri":"Amazon Flex早班7-11am + Skip午餐","Sat-Sun":"Skip全天高峰"},"monthly":1800,"fastest_cash":"DoorDash — 即时提现","start_today":"去 dasher.doordash.com 注册，明天开始","winter_tip":"冬天开车比骑车安全，备手套暖宝宝","deductions":["手机费50%","汽油","保险按比例"]}
    summary = json.dumps([{"name":p["name"],"type":p["type"],"hourly":p["hourly"],"peak":p["peak"][:1],"payout":p["payout"]} for p in PLATFORMS], ensure_ascii=False)
    now = datetime.datetime.now()
    season = "winter" if now.month in [12,1,2] else "spring" if now.month in [3,4,5] else "summer" if now.month in [6,7,8] else "fall"
    prompt = f"""Winnipeg Manitoba gig optimizer. Season:{season}. Platforms:{summary}.
Design optimal weekly delivery income strategy. Respond ONLY JSON (no markdown):
{{"combo":["name1","name2"],"schedule":{{"Mon-Fri":"plan","Sat-Sun":"plan"}},"monthly":1800,"fastest_cash":"platform — reason","start_today":"exact step NOW","winter_tip":"Winnipeg cold weather tip","deductions":["item1","item2","item3"]}}"""
    try:
        r = requests.post(GROQ_URL,
            headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"},
            json={"model":GROQ_MODEL,"messages":[{"role":"user","content":prompt}],"max_tokens":500,"temperature":0.3},
            timeout=25)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw: raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  [groq] {e}")
        return {"combo":["SkipTheDishes","Amazon Flex"],"schedule":{"Mon-Fri":"Amazon Flex早班+Skip午餐","Sat-Sun":"Skip全天"},"monthly":1800,"fastest_cash":"DoorDash即时提现","start_today":"去dasher.doordash.com注册","winter_tip":"备暖手套，车内放备用充电器","deductions":["手机50%","汽油","保险"]}

def run():
    print(f"[Delivery] Starting — {datetime.datetime.now()}")
    strategy = groq_strategy()
    today = datetime.date.today().strftime("%Y-%m-%d")

    # 消息1: 策略
    combo = strategy.get("combo",[])
    msg1 = [f"*🚗 送餐/快递收入规划 {today}*", f"*月收入预测: ${strategy.get('monthly',0)} CAD*","",
            f"*推荐组合: {' + '.join(combo)}*","*每周时间表:*"]
    for day, plan in strategy.get("schedule",{}).items():
        msg1.append(f"  *{day}:* {plan}")
    msg1 += [f"\n*最快到账:* {strategy.get('fastest_cash','')}",
             f"\n*今天第一步:*\n_{strategy.get('start_today','')}_"]
    send_message("\n".join(msg1))

    # 消息2: 平台对比
    msg2 = ["*📊 温尼伯配送平台全览*",""]
    for p in PLATFORMS:
        inc = calc_income(p)
        msg2 += [
            f"{p['emoji']} *{p['name']}* [{p['type']}]",
            f"  时薪~${p['hourly']}/hr | 月净~${inc['net']}",
            f"  高峰: {p['peak'][0]}",
            f"  注册: {p['signup_time']} | 首付: {p['payout']}",
            f"  ✓ {p['pros'][0]}  ✗ {p['cons'][0]}",
            f"  [立即注册]({p['signup']})",""
        ]
    send_message("\n".join(msg2))

    # 消息3: 税务+收入表
    msg3 = ["*💰 3小时/天收入估算 (5天/周)*",""]
    for p in PLATFORMS:
        inc = calc_income(p)
        msg3.append(f"{p['emoji']} {p['name']}: 周${inc['weekly']} → 月净${inc['net']}")
    msg3 += ["","*❄️ 冬季提示:*", f"_{strategy.get('winter_tip','')}_","","*可抵税项目:*"]
    for d in strategy.get("deductions",[]):
        msg3.append(f"  • {d}")
    send_message("\n".join(msg3))

    with db_cursor() as (cur,_):
        cur.execute("INSERT INTO raw_events (source,category,title,content,url) VALUES ('delivery_scanner','gig_income','送餐快递收入规划',%s,'https://skipthedishes.com/driver')",
            (json.dumps(strategy),))
    log_push("telegram","delivery_scanner",{"monthly":strategy.get("monthly")})
    print(f"[Delivery] Done")

if __name__ == "__main__":
    run()
