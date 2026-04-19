#!/usr/bin/env python3
"""
rag/knowledge_base.py
温尼伯生存RAG知识库
运行在 .18 (Acer brain)

功能:
  1. 内置温尼伯生存知识（福利/租房/交通/食物/法律）
  2. 用 nomic-embed-text 生成向量
  3. 存入 ChromaDB
  4. 提供 query() 接口供 L3 冷静层调用
"""
import os
import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = "/home/heng/super-ego-os/rag/db"
OLLAMA_URL  = "http://192.168.0.18:11434"

WINNIPEG_KNOWLEDGE = [
    # 福利
    {"id":"w001","topic":"rent_assist","text":"Manitoba Rent Assist helps low-income renters. Apply at Manitoba Housing. Need: proof of income, lease, ID. Monthly benefit up to $300 depending on income. Apply anytime at 204-945-4663."},
    {"id":"w002","topic":"caip","text":"Canada Carbon Rebate (CAIP) was discontinued in April 2025. No longer available. Previous recipients received quarterly payments."},
    {"id":"w003","topic":"gst_credit","text":"GST/HST Credit paid quarterly: Jan, Apr, Jul, Oct. Single person gets ~$140/quarter. Apply via tax return. No separate application needed if you file taxes."},
    {"id":"w004","topic":"dental","text":"Canada Dental Care Plan covers low-income Canadians. Apply at Canada.ca/dental. Covers cleanings, fillings, extractions. Income under $90k/year. Deadline June 2026."},
    {"id":"w005","topic":"ei","text":"Employment Insurance: apply within 4 weeks of losing job. Need 420-700 hours of insurable work. Pays 55% of earnings up to max. Apply at canada.ca/ei."},
    {"id":"w006","topic":"ccb","text":"Canada Child Benefit: tax-free monthly payment for families with children under 18. Apply via CRA My Account or Service Canada. Based on family income."},
    # 租房
    {"id":"w007","topic":"rental","text":"Winnipeg average rent 2024: 1BR $1,200-1,500/mo, 2BR $1,400-1,800/mo. Cheapest areas: North End, Transcona, West End. Avoid: paying first month without viewing, no written lease."},
    {"id":"w008","topic":"rental_rights","text":"Manitoba tenants rights: landlord must give 24hr notice before entry. Can only raise rent once per year. Max rent increase 2025: 3%. File complaints at Residential Tenancies Branch: 204-945-2476."},
    {"id":"w009","topic":"rental_risk","text":"Rental red flags in Winnipeg: no lease offered, cash only, pressure to decide same day, price too low for area, landlord won't show ID. Always get written lease before paying."},
    # 食物
    {"id":"w010","topic":"food_bank","text":"Winnipeg Harvest food bank: free food, no questions. 1085 Winnipeg Ave. Mon-Fri 9am-4pm. Also: Salvation Army, Community kitchens, Harvest Moon food boxes $5-15."},
    {"id":"w011","topic":"cheap_grocery","text":"Cheapest groceries in Winnipeg: No Frills (budget), Food Fare (local deals), Walmart Supercentre. Check Flipp app weekly. Best deals: buy store brand, shop Wednesday flyer day."},
    {"id":"w012","topic":"free_food","text":"Free meals Winnipeg: Siloam Mission (daily meals, 300 Princess St), Main Street Project, Aboriginal Health & Wellness Centre, various churches Sunday meals."},
    # 交通
    {"id":"w013","topic":"transit","text":"Winnipeg Transit adult fare: $3.15 cash, $2.43 with Peggo card. Monthly pass $104. Low-income monthly pass available for $60 if on EIA/Rent Assist. Call 311 to apply."},
    {"id":"w014","topic":"transit_routes","text":"Key Winnipeg bus routes: Route 16 (main north-south), Route 18 (downtown-south), Route 11 (McPhillips). BLUE rapid transit: faster downtown. Plan trips at winnipegtransit.com."},
    # 法律/权利
    {"id":"w015","topic":"legal_aid","text":"Free legal help Winnipeg: Legal Aid Manitoba 204-985-8500 (income-tested), Community Legal Education Association (CLEA) free clinics, Law Phone-In Tuesdays 6-8pm."},
    {"id":"w016","topic":"employment_rights","text":"Manitoba minimum wage 2025: $15.80/hour. Entitled to: overtime after 8hrs/day, 2 weeks vacation after 1 year, no illegal deductions. File complaints: Manitoba Employment Standards 204-945-3352."},
    # 财务
    {"id":"w017","topic":"financial_risk","text":"High-risk financial products to avoid in Canada: payday loans (400%+ APR), rent-to-own furniture, title loans. Instead: credit union emergency loans, community organizations, Manitoba financial assistance."},
    {"id":"w018","topic":"banking","text":"Free banking options Winnipeg: Steinbach Credit Union, Cambrian Credit Union (free chequing). No-fee accounts: Tangerine, Simplii Financial. Avoid: $15+/mo bank fees."},
    {"id":"w019","topic":"debt","text":"Manitoba debt help: Credit Counselling Society free service 1-888-527-8999. Do NOT pay for credit repair services. Bankruptcy trustee consultation is free. Student loans: repayment assistance plan available."},
    # 医疗
    {"id":"w020","topic":"health","text":"Manitoba Health Card (PHIN): apply at any Service Manitoba. Free doctor visits, hospital. No coverage: dental, vision, most prescriptions. Manitoba Pharmacare: caps drug costs based on income."},
    {"id":"w021","topic":"mental_health","text":"Free mental health Winnipeg: Klinic Community Health (204-784-4090, 24hr crisis line), Mobile Crisis Service 204-940-1781, CMHA Manitoba. No referral needed for many services."},
    # 冬季生存
    {"id":"w022","topic":"winter","text":"Winnipeg winter survival: windchill can reach -50C. Frostbite risk below -25C. Free warming centres open when temp drops below -25C: check City of Winnipeg website or call 311. Always layer clothing."},
    {"id":"w023","topic":"heating","text":"Manitoba Hydro budget billing: spread heating costs evenly. Low-income: Manitoba Hydro financial assistance, EIA covers utilities. If facing disconnection: call Manitoba Hydro 204-360-7999 immediately."},
    # 决策智慧
    {"id":"w024","topic":"impulse_buying","text":"Impulse purchase rule: items over $100 — wait 48 hours. Items over $500 — wait 1 week. Check: Can I buy this used? Do I already own something similar? Will I use this in 6 months?"},
    {"id":"w025","topic":"scams","text":"Common Winnipeg scams: fake rental listings (Kijiji), utility disconnection phone scams, CRA phone scams (CRA never calls first), job offer requiring upfront payment. If unsure, hang up and call official number."},
]

def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.OllamaEmbeddingFunction(
        url=f"{OLLAMA_URL}/api/embeddings",
        model_name="nomic-embed-text"
    )
    return client.get_or_create_collection(
        name="winnipeg_survival",
        embedding_function=ef
    )

def build_index():
    print("[RAG] Building Winnipeg survival knowledge index...")
    collection = get_collection()
    existing = collection.get()["ids"]
    new_docs = [d for d in WINNIPEG_KNOWLEDGE if d["id"] not in existing]
    if not new_docs:
        print(f"[RAG] Already indexed {len(existing)} documents")
        return
    collection.add(
        ids=[d["id"] for d in new_docs],
        documents=[d["text"] for d in new_docs],
        metadatas=[{"topic": d["topic"]} for d in new_docs]
    )
    print(f"[RAG] Indexed {len(new_docs)} documents ({len(existing)} already existed)")

def query(question: str, n_results: int = 3) -> list[str]:
    collection = get_collection()
    results = collection.query(query_texts=[question], n_results=n_results)
    return results["documents"][0] if results["documents"] else []

if __name__ == "__main__":
    build_index()
    print("\n[RAG] Test query: 'rent assist application'")
    results = query("how to apply for rent assist winnipeg")
    for r in results:
        print(f"  → {r[:100]}")
