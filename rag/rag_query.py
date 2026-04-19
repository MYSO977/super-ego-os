#!/usr/bin/env python3
"""
rag/rag_query.py
RAG查询接口 — 供L3冷静层和其他模块调用
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rag.knowledge_base import query

def get_context(question: str, n: int = 3) -> str:
    docs = query(question, n_results=n)
    if not docs:
        return ""
    return "\n".join([f"- {d}" for d in docs])

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "cheap food winnipeg"
    print(f"Query: {q}\n")
    print(get_context(q))
