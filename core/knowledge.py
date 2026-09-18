"""知识库加载：读取 knowledge/ 下的 Markdown，清洗成可以直接切块的文本"""
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


def clean(text):
    """规范化知识库文本：去掉空行，再在标题行 / Q 行前补一个空行。

    补空行是因为下游按空行切块：标题要独立成块，Q 行要和它的 A 行黏在一起。
    """
    out = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        # 标题行和 Q 行前面补一个空行，作为切块的分界（A 行要紧跟 Q 行）
        if (line.startswith("#") or line.startswith("Q：")) and out:
            out.append("")
        out.append(line)

    return "\n".join(out)


def load_knowledge():
    """把所有知识库文件清洗后拼成一段完整文本。

    注意不要把文件名拼进正文 —— 那会生成一堆只含 "faq.md" 这类词的空壳块，
    既没有实质内容，又照样参与检索排名。
    """
    parts = [clean(f.read_text(encoding="utf-8")) for f in sorted(KNOWLEDGE_DIR.glob("*.md"))]
    return "\n\n".join(parts)


if __name__ == "__main__":
    text = load_knowledge()
    print(f"共 {len(text)} 个字符\n")
    print(text)
