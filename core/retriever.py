"""知识库检索：切块 → 查询改写 → BM25 打分 → 两道闸门 → 拼参考资料。

两道闸门决定"要不要把资料喂给模型"，这是防幻觉的第一层：

闸门 1（实体命中）
    用户问题里必须出现至少一个"知识库实体"（商品名，或知识块首行里的实词）。
    一个实体都没命中，就直接告诉模型"没检索到"，不给它任何资料。
    没有这道闸门时，『你们的眼霜能用吗』会因为"能用吗"这类句式词命中语料，
    把『敏感肌能用吗』『运费谁承担？』等完全无关的资料塞给模型 —— 而模型看到
    "孕妇可用""敏感肌可用"，很容易顺着说出"眼霜孕妇可以用"。

闸门 2（相对分数）
    BM25 分数没有归一化，绝对值会随语料规模漂移，钉死一个 0.5 没有意义
    （实测在本项目语料里，单个词命中一次就有 1.9~2.7 分，阈值形同虚设）。
    改成相对判断：只保留分数达到 top1 一定比例的块，避免弱相关块稀释上下文。
"""
import logging

import jieba
import jieba.posseg as pseg
from rank_bm25 import BM25Okapi

from core.knowledge import KNOWLEDGE_DIR, load_knowledge
from core.llm import chat

jieba.setLogLevel(logging.WARNING)

# 商品名加权倍数。用乘法而不是加常数：加常数会把块之间的原始相关性差距压平
# （实测『面膜多少钱』原为 0.82 vs 0.74，各加 5 分后变成 5.82 vs 5.74，排序形同虚设）。
NAME_BOOST = 1.5

# 只保留分数达到 top1 该比例的块
REL_SCORE_RATIO = 0.5

NO_HIT = "（知识库中没有检索到相关内容）"

# 命中这些词不代表"问到了知识库里的东西"，构建实体表和判定时都要跳过
STOPWORDS = set(
    "的 了 吗 呢 吧 啊 哦 呀 嘛 是 有 能 会 要 想 可以 能用 帮 给 和 与 跟 对 从 到 就 都 也 "
    "很 太 还 再 又 只 被 把 让 用 什么 怎么 怎么样 如何 是否 这个 那个 这 那 我们 你们 "
    "他们 咱 请问 一下 一个 支持 现在 目前 还有 但是 因为 所以 如果 或者 麻烦 谢谢 你好 您好".split()
)

# 这些词性的词不作为实体（虚词、代词、数量词、时间词等）
SKIP_FLAGS = ("x", "w", "u", "y", "e", "o", "r", "p", "c", "d", "m", "q", "t", "f", "s", "b", "z")

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


# ---------------------------------------------------------------------------
# 索引缓存：知识库只在首次使用、或文件被改动时读盘 + 分词，不用每次提问都重算
# ---------------------------------------------------------------------------
_CACHE = {
    "mtime": None,
    "chunks": None,
    "bm25": None,
    "entities": None,
    "products": None,
    "product_idx": None,
}


def _knowledge_mtime():
    """索引新鲜度指纹：文件数 + 最大修改时间。

    只取 max 不够 —— 删掉一个"不是最新"的 md 文件时 max 不变，
    缓存不重建，被删掉的内容会继续参与检索。
    """
    files = list(KNOWLEDGE_DIR.glob("*.md"))
    return (len(files), max((f.stat().st_mtime for f in files), default=0.0))


def _extract_entities(chunks):
    """从知识库自动提取实体词：商品名 + 每个知识块首行里的实词。

    不限定只收名词 —— 『怎么退货』『退款多久到账』这类问题的关键信息是动词性的
    业务词，只收名词会把它们全部误判成"没检索到"。
    """
    entities = set()
    products = set()
    for chunk in chunks:
        head = chunk.split("\n")[0].strip()
        if head.startswith("## "):
            name = head[3:].replace("XX", "").strip()
            if len(name) >= 2:
                entities.add(name)
                products.add(name)
        elif head.startswith("Q："):
            for word, flag in pseg.cut(head[2:]):
                if len(word) < 2 or word in STOPWORDS:
                    continue
                if flag[0] in SKIP_FLAGS:
                    continue
                entities.add(word)
    return entities, products


def _index():
    """返回索引缓存（必要时重建）：chunks / bm25 / entities / products / product_idx"""
    mtime = _knowledge_mtime()
    if _CACHE["mtime"] != mtime:
        chunks = split_chunks(load_knowledge())
        bm25 = BM25Okapi([tokenize(c) for c in chunks])
        entities, products = _extract_entities(chunks)
        # 商品详情块（首行是 "## 商品名"），商品名加权只对它们生效
        product_idx = [
            i for i, c in enumerate(chunks) if c.split("\n")[0].strip().startswith("## ")
        ]
        _CACHE.update(
            mtime=mtime,
            chunks=chunks,
            bm25=bm25,
            entities=entities,
            products=products,
            product_idx=product_idx,
        )
    return _CACHE


def reload():
    """强制重建索引（知识库改完想立刻生效时调用）"""
    _CACHE["mtime"] = None
    _index()


def entities_in(query):
    """问题里命中的知识库实体"""
    return sorted(e for e in _index()["entities"] if e in query)


def search(query, top_k=3):
    """检索：改写词 + 原词一起算，并对问题里提到的商品加权"""
    key = rewrite(query)
    idx = _index()
    chunks, bm25 = idx["chunks"], idx["bm25"]

    # 改写词和原词一起参与打分，改写跑偏时原词兜底
    scores = list(bm25.get_scores(tokenize(key) + tokenize(query)))

    # 用户明确提到的商品：只对「商品详情块」加权，让它在排序里稳定胜出。
    # 注意不是"任何包含商品名的块" —— 否则『面膜多少钱』会把提到面膜的 FAQ 块
    # 一起抬上来，context 里塞进『孕妇可以用吗』这类无关内容。
    for name in idx["products"]:
        if name in query:
            for i in idx["product_idx"]:
                if name in chunks[i]:
                    scores[i] *= NAME_BOOST

    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return key, ranked[:top_k]


def build_context(question):
    """检索并拼成参考资料；没有命中知识库实体就明确告诉模型"没找到" """
    # 闸门 1：一个问题都没碰到知识库实体，就不要给模型任何资料
    if not entities_in(question):
        return NO_HIT

    # 闸门 2：只保留与 top1 同量级的块
    _, hits = search(question)
    if not hits or hits[0][1] <= 0:
        return NO_HIT

    top1 = hits[0][1]
    good = [chunk for chunk, score in hits if score >= top1 * REL_SCORE_RATIO]
    return "\n\n".join(good) if good else NO_HIT
