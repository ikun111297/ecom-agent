from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


def clean(text):
    """规范化知识库文本：清掉转义符和多余空行，保证切块正确"""
    text = text.replace("\\#", "#").replace("\\-", "-").replace("\\*", "*")

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
    """读取 knowledge 目录下所有 .md 文件，清洗后拼成一段完整文本"""
    parts = []
    for f in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = clean(f.read_text(encoding="utf-8"))
        parts.append(f"===== {f.name} =====\n{content}")
    return "\n\n".join(parts)


if __name__ == "__main__":
    text = load_knowledge()
    print(f"共 {len(text)} 个字符\n")
    print(text)