#!/usr/bin/env python3
"""
L3 Super-Ego Cooling Layer v2 — with RAG context
运行在 .18 (有RAG知识库) 或 .11
"""
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
OLLAMA_URL   = "http://192.168.0.18:11434/api/generate"

def get_rag_context(decision_text: str) -> str:
    try:
        from rag.rag_query import get_context
        return get_context(decision_text)
    except Exception as e:
        print(f"  [rag] unavailable: {e}")
        return ""

def qwen_analyze(decision_text: str, rag_context: str) -> dict:
    context_section = f"\nRelevant local knowledge:\n{rag_context}" if rag_context else ""
    prompt = f"""Rational advisor helping avoid impulsive decisions.
Decision: {decision_text}{context_section}
Respond ONLY with JSON:
{{"pros":["pro1","pro2"],"cons":["con1","con2"],"risks":["risk1","risk2"],"alternatives":["alt1","alt2"],"impulse_score":7}}
impulse_score 0-10 (10=very impulsive). Max 3 per list."""
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": "qwen2.5:0.5b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 500, "temperature": 0.3}
        }, timeout=60)
        r.raise_for_status()
        raw = r.json().get("response","").strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        print(f"  [qwen] error: {e}")
        return {"pros":["Possible benefit"],"cons":["Costs money","May not need"],"risks":["Budget impact"],"alternatives":["Wait 30 days","Buy used"],"impulse_score":6}

def groq_recommend(decision_text: str, analysis: dict, rag_context: str) -> dict:
    if not GROQ_API_KEY:
        return {"verdict":"pause","recommendation":"Wait before deciding","cooling_hours":24,"anti_human_insight":"","first_principles":"","frame_recast":""}
    context_section = f"\nLocal resources available:\n{rag_context}" if rag_context else ""
    prompt = f"""Decision: {decision_text}
Analysis — Pros: {analysis['pros']} | Cons: {analysis['cons']} | Risks: {analysis['risks']} | Impulse: {analysis['impulse_score']}/10
{context_section}
Person: Winnipeg MB, budget-conscious, values long-term stability.

Apply THREE reasoning frameworks:
1. First principles: break down to fundamental needs
2. Inversion: what happens if this goes wrong
3. Frame recast: reframe loss as cost, opportunity as gift

Respond ONLY with JSON (no markdown):
{{"verdict":"pause","recommendation":"one clear sentence","cooling_hours":24,"anti_human_insight":"uncomfortable truth","first_principles":"fundamental need analysis","frame_recast":"reframed perspective"}}
verdict: go/pause/stop"""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, headers=headers, json={
            "model": GROQ_MODEL,
            "messages": [{"role":"user","content":prompt}],
            "max_tokens": 400, "temperature": 0.2
        }, timeout=20)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        return {"verdict":"pause","recommendation":"Wait before deciding","cooling_hours":24,"anti_human_insight":"","first_principles":"","frame_recast":""}

def save_decision(decision_text, analysis, rec):
    cooling_h = rec.get("cooling_hours", 24)
    revisit   = datetime.datetime.now() + datetime.timedelta(hours=cooling_h)
    with db_cursor() as (cur, _):
        cur.execute("""
            INSERT INTO ego_decisions (topic, pros, cons, risk_list, alternatives, recommendation, cooling_hours, revisit_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (decision_text, json.dumps(analysis.get("pros",[])), json.dumps(analysis.get("cons",[])),
              json.dumps(analysis.get("risks",[])), json.dumps(analysis.get("alternatives",[])),
              rec.get("recommendation",""), cooling_h, revisit))
        return cur.fetchone()["id"]

VERDICT_EMOJI = {"go":"✅","pause":"⏸","stop":"🛑"}

def format_msg(decision_text, analysis, rec, dec_id):
    verdict = rec.get("verdict","pause")
    emoji   = VERDICT_EMOJI.get(verdict,"⏸")
    cooling = rec.get("cooling_hours",24)
    revisit = (datetime.datetime.now() + datetime.timedelta(hours=cooling)).strftime("%m-%d %H:%M")
    lines = [
        f"*🧠 超我分析 v2 #{dec_id}*",
        f"*决策:* {decision_text}", "",
        f"*判决: {emoji} {verdict.upper()}*",
        f"_{rec.get('recommendation','')}_", "",
        "*优点:*"] + [f"  + {p}" for p in analysis.get("pros",[])] + [
        "*风险/缺点:*"] + [f"  - {c}" for c in analysis.get("cons",[]) + analysis.get("risks",[])] + [
        "*替代方案:*"] + [f"  → {a}" for a in analysis.get("alternatives",[])]
    if rec.get("first_principles"):
        lines += ["", f"*第一性原理:* _{rec['first_principles']}_"]
    if rec.get("frame_recast"):
        lines += [f"*重新框架:* _{rec['frame_recast']}_"]
    if rec.get("anti_human_insight"):
        lines += ["", f"*你不想听但必须听:*\n_{rec['anti_human_insight']}_"]
    lines += [f"\n*冷静期:* {cooling}h → 再看: {revisit}"]
    return "\n".join(lines)

def run(decision_text: str):
    print(f"[L3v2] Analyzing: {decision_text[:60]}")
    rag_context = get_rag_context(decision_text)
    print(f"  rag_context: {len(rag_context)} chars")
    analysis = qwen_analyze(decision_text, rag_context)
    print(f"  impulse_score={analysis.get('impulse_score')}")
    rec      = groq_recommend(decision_text, analysis, rag_context)
    print(f"  verdict={rec.get('verdict')} cooling={rec.get('cooling_hours')}h")
    dec_id   = save_decision(decision_text, analysis, rec)
    msg      = format_msg(decision_text, analysis, rec, dec_id)
    send_message(msg)
    log_push("telegram","super_ego_v2",{"id":dec_id,"verdict":rec.get("verdict")})
    print(f"[L3v2] Decision #{dec_id} saved and pushed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("decision", nargs="?", default=None)
    args = parser.parse_args()
    if args.decision:
        run(args.decision)
    else:
        print("Super-Ego v2 冷静层 (Ctrl+C 退出)")
        while True:
            try:
                text = input("\n决策: ").strip()
                if text:
                    run(text)
            except KeyboardInterrupt:
                break
