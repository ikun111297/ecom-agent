import logging

import jieba
from rank_bm25 import BM25Okapi

from core.knowledge import load_knowledge
from core.llm import chat

jieba.setLogLevel(logging.WARNING)

MIN_SCORE = 0.5
NAME_BOOST = 5.0

REWRITE_PROMPT = """把用户的口语问题改写成适合检索的关键词。
要求：只输出关键词，用空格分隔，不要标点，不要解释。

用户问题：敏感肌能用吗
关键词：敏感肌 适用

用户问题：精华多少钱
关键词：精华 价格

用户问题：{}"""


def split_chunks(text):
    """按空行把知识库切成小块，每块是一个独立知识点"""
    blocks = [b.strip() for b in text.split("\n\n")]
    return [b for b in blocks if len(b) >= 20]


def tokenize(text):
    """中文分词"""
    return [w for w in jieba.cut(text) if w.strip()]


def rewrite(query):
    """把口语问题改写成关键词（temperature=0 保证稳定）"""
    resp = chat(
        [{"role": "user", "content": REWRITE_PROMPT.format(query)}],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


def product_names():
    """从知识库里提取所有商品名（## 标题）"""
    names = []
    for chunk in split_chunks(load_knowledge()):
        first_line = chunk.split("\n")[0]
        if first_line.startswith("## "):
            names.append(first_line[3:].strip())
    return names


def search(query, top_k=3):
    """检索：改写词 + 原词一起算，并对问题里提到的商品加权"""
    key = rewrite(query)

    chunks = split_chunks(load_knowledge())
    bm25 = BM25Okapi([tokenize(c) for c in chunks])

    # 改写词和原词一起参与打分，改写跑偏时原词兜底
    scores = list(bm25.get_scores(tokenize(key) + tokenize(query)))

    # 问题里明确提到的商品，把它对应那块大幅加分，避免被其他商品挤掉
    for name in product_names():
        core = name.replace("XX", "").strip()
        if core and core in query:
            for i, chunk in enumerate(chunks):
                if name in chunk:
                    scores[i] += NAME_BOOST

    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return key, ranked[:top_k]


def build_context(question):
    """检索并拼成参考资料；一块都没找到就明确告诉模型"""
    _, hits = search(question)
    good = [chunk for chunk, score in hits if score >= MIN_SCORE]

    if not good:
        return "（知识库中没有检索到相关内容）"

    return "\n\n".join(good)