#!/usr/bin/env python3
"""
rag/manitoba_law.py
曼省法律库 + 本地资源扩充
运行: python3 rag/manitoba_law.py
会把新知识追加到现有 ChromaDB
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rag.knowledge_base import get_collection

LEGAL_KNOWLEDGE = [
    # 租户权利法
    {"id":"l001","topic":"tenancy_law","text":"Manitoba Residential Tenancies Act: landlord cannot evict without proper notice. Month-to-month: 3 months notice. Fixed term: must wait until end of term. Illegal eviction: call RTB 204-945-2476 immediately."},
    {"id":"l002","topic":"eviction_rights","text":"Illegal reasons to evict in Manitoba: race, gender, disability, family status, source of income. If evicted illegally: file complaint with Manitoba Human Rights Commission 204-945-3007. Free process."},
    {"id":"l003","topic":"security_deposit","text":"Manitoba security deposit law: maximum half month rent. Must be returned within 14 days of moving out with written statement. Interest must be paid on deposit. File complaint at RTB if not returned."},
    {"id":"l004","topic":"repairs","text":"Manitoba landlord repair obligations: must maintain property in good repair. Heat must be provided. If landlord refuses repairs: write letter, keep copy, report to RTB. Rent can be reduced by RTB for ongoing issues."},
    {"id":"l005","topic":"rent_increase","text":"Manitoba rent increase rules 2025: maximum 3% per year. Must give 3 months written notice. Cannot increase more than once per year. Illegal increases: file complaint at RTB, no cost to tenant."},
    # 劳工法
    {"id":"l006","topic":"employment_law","text":"Manitoba Employment Standards: minimum wage $15.80/hr (2025). Overtime: 1.5x after 8hrs/day or 40hrs/week. Statutory holidays: 9 days/year paid. Termination: 1 week notice per year of service up to 8 weeks."},
    {"id":"l007","topic":"wrongful_dismissal","text":"Wrongful dismissal Manitoba: if fired without cause and insufficient notice, file complaint at Employment Standards within 6 months. Free process. Can recover lost wages. Call 204-945-3352."},
    {"id":"l008","topic":"workplace_safety","text":"Manitoba workplace safety: right to refuse unsafe work without penalty. Report injuries within 5 days to WCB (Workers Compensation Board). WCB covers medical costs and lost wages. 204-954-4321."},
    {"id":"l009","topic":"ei_rights","text":"EI rights: cannot be disqualified for leaving job due to harassment, unsafe conditions, or family emergency. Appeal EI decisions within 30 days. Social Security Tribunal handles appeals, free service."},
    # 消费者保护
    {"id":"l010","topic":"consumer_protection","text":"Manitoba Consumer Protection Act: 10-day cooling off period for door-to-door sales. Used car: 30-day warranty minimum. False advertising: file complaint with Consumer Protection Office 204-945-3800."},
    {"id":"l011","topic":"payday_loans","text":"Manitoba payday loan law: maximum $17 per $100 borrowed (rate capped). Lender must give 48hr cancellation right. Cannot roll over loans. File complaint: Consumer Protection Office. Better option: credit union emergency loan."},
    {"id":"l012","topic":"debt_collection","text":"Manitoba debt collection rules: collectors cannot call before 8am or after 9pm. Cannot contact employer without permission. Cannot threaten arrest. If harassed: write cease contact letter, file complaint with Consumer Protection."},
    {"id":"l013","topic":"credit_rights","text":"Credit report rights Canada: free credit report from Equifax and TransUnion once per year. Errors must be corrected within 30 days. Negative items removed after 6-7 years. File dispute directly with credit bureau, free."},
    # 移民相关
    {"id":"l014","topic":"immigration_rights","text":"Immigrant rights Manitoba: all workers entitled to employment standards regardless of immigration status. Temporary workers: same minimum wage, overtime, holiday pay as citizens. Report violations anonymously: 204-945-3352."},
    {"id":"l015","topic":"refugee_support","text":"Refugee support Winnipeg: Immigration Partnership Winnipeg 204-949-0234. Manitoba Interfaith Immigration Council. IRCOM (Immigrant and Refugee Community Organization). Settlement services, language training, employment help."},
    {"id":"l016","topic":"pr_pathway","text":"Manitoba Provincial Nominee Program (MPNP): pathways for skilled workers, international students, business investors. Processing time 12-18 months. Free application through province. Avoid immigration consultants charging upfront fees."},
    # 本地资源扩充
    {"id":"r001","topic":"emergency_help","text":"Winnipeg emergency resources: 211 Manitoba (24/7 helpline for any social service), Klinic 204-784-4090 (crisis), Osborne House 204-942-3052 (domestic violence shelter), Main Street Project 204-982-8245 (homeless support)."},
    {"id":"r002","topic":"free_services","text":"Free services Winnipeg: public library (free internet, printing, programs), Immigrant Centre Manitoba (free settlement), SEED Winnipeg (free financial counseling), BizConnect (free business advice), North End Community Renewal (various free programs)."},
    {"id":"r003","topic":"disability_benefits","text":"Disability benefits Manitoba: CPP Disability (federal), AISH alternative through EIA, Manitoba Disability Tax Credit. Apply through Service Canada or Manitoba Families. Free assistance applying: Independent Living Resource Centre 204-947-0194."},
    {"id":"r004","topic":"seniors_resources","text":"Seniors resources Winnipeg: Age & Opportunity 204-956-6440 (free programs), Seniors Abuse Line 1-888-896-7183, Free tax clinics for seniors (CVITP), Manitoba Pharmacare Seniors benefit, Home care through Manitoba Health."},
    {"id":"r005","topic":"child_services","text":"Child services Winnipeg: DCFS (Child and Family Services) 204-944-4200, free daycares for low-income families (subsidy program), Early Learning and Child Care subsidy, Child Tax Benefit, Healthy Baby prenatal program."},
    # 财务法律
    {"id":"f001","topic":"bankruptcy_law","text":"Bankruptcy Manitoba: filing fee ~$1,800 but trustee payment plans available. Protects: basic furniture, one vehicle up to $3,000, tools of trade, RRSP contributions over 12 months old. Most unsecured debts discharged. Free consultation with Licensed Insolvency Trustee."},
    {"id":"f002","topic":"garnishment","text":"Manitoba wage garnishment: creditors can garnish wages only with court order. Exempt: 70% of net wages or minimum wage x 40hrs/week, whichever is greater. Bank account: $2,000 exempt from garnishment. File exemption claim immediately if garnished."},
    {"id":"f003","topic":"tax_credits","text":"Manitoba tax credits available: Property Tax Credit (up to $700), Education Property Tax Rebate, Political Contribution Tax Credit, Manitoba Green Energy Equipment Tax Credit, Film and Video Production Tax Credit. File via T1 tax return."},
    {"id":"f004","topic":"free_tax_filing","text":"Free tax filing Manitoba: CVITP (Community Volunteer Income Tax Program) — free for income under $35k or simple returns. Locations: libraries, community centres, United Way. File taxes even if no income — needed to receive benefits (GST, CCB, Pharmacare)."},
    # 心理健康法律权利
    {"id":"m001","topic":"mental_health_law","text":"Manitoba Mental Health Act: voluntary admission preferred. Involuntary: only if danger to self/others AND mental disorder. Patients have rights: legal counsel, second opinion, appeal to Mental Health Review Board. Rights advisor available free in hospital."},
    {"id":"m002","topic":"accommodation_rights","text":"Manitoba Human Rights Code: employers and landlords must accommodate mental health conditions to point of undue hardship. Cannot be fired for mental health leave. Accommodation requests in writing. File complaint: Manitoba Human Rights Commission, free process."},
]

def add_legal_knowledge():
    print("[RAG] Adding Manitoba legal + resource knowledge...")
    collection = get_collection()
    existing = set(collection.get()["ids"])
    new_docs = [d for d in LEGAL_KNOWLEDGE if d["id"] not in existing]
    if not new_docs:
        print(f"[RAG] All {len(LEGAL_KNOWLEDGE)} documents already indexed")
        return
    collection.add(
        ids=[d["id"] for d in new_docs],
        documents=[d["text"] for d in new_docs],
        metadatas=[{"topic": d["topic"]} for d in new_docs]
    )
    total = len(existing) + len(new_docs)
    print(f"[RAG] Added {len(new_docs)} documents. Total: {total}")

if __name__ == "__main__":
    add_legal_knowledge()
    from rag.knowledge_base import query
    print("\n[RAG] Test: 'landlord not returning deposit'")
    for r in query("landlord not returning security deposit", n_results=2):
        print(f"  → {r[:120]}")
    print("\n[RAG] Test: '被老板解雇没有通知'")
    for r in query("fired without notice employment rights", n_results=2):
        print(f"  → {r[:120]}")
