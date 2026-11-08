from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional dependency is checked at runtime
    fitz = None


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}
MAX_TEXT_CHARS = 180_000

STOPWORDS = {
    "这个",
    "那个",
    "我们",
    "他们",
    "已经",
    "进行",
    "由于",
    "如果",
    "需要",
    "可能",
    "可以",
    "以及",
    "但是",
    "因为",
    "所以",
    "对于",
    "关于",
    "一个",
    "一些",
    "怎么",
    "怎么变化",
    "变化",
    "发布",
    "之后",
    "以后",
    "当前",
    "预测",
    "问题",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "will",
    "risk",
}

FACTOR_PATTERNS = [
    ("政策监管", ("政策", "监管", "法规", "审批", "合规", "监管", "regulation", "policy")),
    ("市场需求", ("市场", "需求", "用户", "客户", "客流", "消费", "market", "demand")),
    ("舆论情绪", ("舆情", "舆论", "媒体", "社交", "评论", "情绪", "public", "media")),
    ("成本资源", ("成本", "资金", "预算", "资源", "人力", "运力", "cost", "resource")),
    ("技术能力", ("技术", "系统", "模型", "算法", "数据", "平台", "technology", "data")),
    ("竞争格局", ("竞争", "对手", "替代", "竞品", "份额", "competition", "rival")),
    ("执行风险", ("风险", "延误", "故障", "缺口", "瓶颈", "不确定", "risk", "delay")),
]

COMMON_ENTITY_PHRASES = [
    "新产品",
    "市场需求",
    "媒体讨论",
    "用户期待",
    "供应链成本",
    "监管审批",
    "执行风险",
    "数据平台",
    "公众接受度",
    "负面舆论",
    "项目节奏",
    "政策",
    "公司",
    "平台",
    "用户",
    "公众",
    "媒体",
    "市场",
    "项目",
    "数据",
]

ALLOWED_SHORT_TERMS = {
    "市场",
    "媒体",
    "用户",
    "公众",
    "公司",
    "平台",
    "成本",
    "监管",
    "风险",
    "政策",
    "产品",
    "项目",
    "数据",
}

NOISE_FRAGMENTS = {
    "怎么",
    "变化",
    "发布后",
    "布后",
    "以后",
    "之后",
    "当前",
    "预测",
    "问题",
}


def decode_text_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("只支持 .txt / .md / .pdf 种子材料")
    if suffix == ".pdf":
        if fitz is None:
            raise ValueError("当前环境未安装 PyMuPDF，无法解析 PDF")
        try:
            chunks: list[str] = []
            with fitz.open(path) as doc:
                for page in doc:
                    chunks.append(page.get_text("text"))
            text = "\n".join(chunks)
        except Exception as exc:
            raise ValueError(f"PDF 解析失败：{exc}") from exc
    else:
        text = decode_text_bytes(path.read_bytes())

    text = normalize_text(text)
    if not text:
        raise ValueError("材料内容为空，无法创建预测项目")
    return text[:MAX_TEXT_CHARS]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_summary(text: str, question: str) -> dict[str, object]:
    sentences = split_sentences(text)
    question_terms = set(extract_terms(question, limit=8))
    scored: list[tuple[int, str]] = []
    for sentence in sentences[:80]:
        terms = set(extract_terms(sentence, limit=20))
        score = len(question_terms & terms) * 3 + min(len(sentence), 120) // 30
        if score > 0:
            scored.append((score, sentence))
    picked = [item for _, item in sorted(scored, reverse=True)[:4]]
    if not picked:
        picked = sentences[:4]
    return {
        "chars": len(text),
        "paragraphs": len([p for p in text.split("\n\n") if p.strip()]),
        "brief": " ".join(picked)[:900],
        "top_terms": extract_terms(text + "\n" + question, limit=12),
    }


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [part.strip() for part in parts if len(part.strip()) >= 10]


def extract_terms(text: str, limit: int = 20) -> list[str]:
    counter: Counter[str] = Counter()
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", text):
        lowered = word.lower()
        if lowered not in STOPWORDS:
            counter[word[:40]] += 2

    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", text):
        if is_noise_term(chunk):
            continue
        if len(chunk) <= 4:
            counter[chunk] += 2
        else:
            for size in (4, 3, 2):
                for idx in range(0, max(1, len(chunk) - size + 1)):
                    term = chunk[idx : idx + size]
                    if not is_noise_term(term):
                        counter[term] += 1
    return [term for term, _ in counter.most_common(limit)]


def extract_entities(text: str, question: str, limit: int = 12) -> list[dict[str, object]]:
    merged = question + "\n" + text
    terms = candidate_entity_terms(merged, limit=limit * 4)
    entities: list[dict[str, object]] = []
    seen: set[str] = set()
    suffix_type = [
        ("组织", ("公司", "平台", "部门", "机构", "团队", "政府", "group", "team")),
        ("地点", ("机场", "城市", "地区", "市场", "区域", "country", "city")),
        ("事件", ("政策", "项目", "计划", "事件", "会议", "活动", "campaign")),
        ("人群", ("用户", "客户", "公众", "旅客", "员工", "社区", "people", "user")),
    ]
    for term in terms:
        normalized = term.strip(" -_")
        lowered = normalized.lower()
        if len(normalized) < 2 or lowered in seen or is_noise_entity(normalized):
            continue
        if any(normalized in existing and len(normalized) < len(existing) for existing in seen):
            continue
        replaced = False
        for existing in list(seen):
            if existing in lowered and len(lowered) > len(existing):
                seen.remove(existing)
                entities = [item for item in entities if str(item.get("name", "")).lower() != existing]
                replaced = True
        if replaced and lowered in seen:
            continue
        seen.add(lowered)
        entity_type = "概念"
        for candidate, markers in suffix_type:
            if any(marker in lowered or marker in normalized for marker in markers):
                entity_type = candidate
                break
        entities.append(
            {
                "name": normalized,
                "type": entity_type,
                "weight": round(0.35 + min(text.count(normalized), 8) * 0.07, 2),
                "evidence": find_evidence_sentence(text, normalized),
            }
        )
        if len(entities) >= limit:
            break
    return entities


def candidate_entity_terms(text: str, limit: int) -> list[str]:
    candidates: list[str] = []
    for phrase in COMMON_ENTITY_PHRASES:
        if phrase in text:
            candidates.append(phrase)
    for category, markers in FACTOR_PATTERNS:
        if category in text or any(marker in text for marker in markers):
            candidates.append(category)
    for term in extract_terms(text, limit=limit):
        if is_fragment_term(term):
            continue
        candidates.append(term)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        clean = clean_entity_term(term)
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        deduped.append(clean)
        if len(deduped) >= limit:
            break
    return deduped


def clean_entity_term(term: str) -> str:
    clean = term.strip()
    for phrase in COMMON_ENTITY_PHRASES:
        if phrase in clean:
            return phrase
    clean = re.sub(r"^(如果|由于|因为|准备|发布|推出|负面|某|该)", "", clean)
    clean = re.sub(r"(仍然|存在|可能|改善|升温|放缓|提升)$", "", clean)
    return clean.strip()


def is_fragment_term(term: str) -> bool:
    if is_noise_entity(term):
        return True
    if term[:1] in {"备", "布", "品", "么", "司", "场", "户", "体"}:
        return True
    if term[-1:] in {"准", "新", "发", "布", "后", "么", "化", "会"}:
        return True
    return False


def is_noise_term(term: str) -> bool:
    stripped = term.strip().lower()
    if not stripped or stripped in STOPWORDS:
        return True
    if any(fragment in stripped for fragment in NOISE_FRAGMENTS):
        return True
    if len(stripped) <= 2 and stripped not in ALLOWED_SHORT_TERMS:
        return True
    if stripped.endswith(("发", "布", "后", "么")):
        return True
    return False


def is_noise_entity(term: str) -> bool:
    if is_noise_term(term):
        return True
    if len(term) <= 2 and term not in ALLOWED_SHORT_TERMS:
        return True
    return False


def extract_factors(text: str, question: str) -> list[dict[str, object]]:
    merged = f"{question}\n{text}"
    factors: list[dict[str, object]] = []
    for category, markers in FACTOR_PATTERNS:
        score = sum(merged.lower().count(marker.lower()) for marker in markers)
        if score:
            direction = "risk" if category in {"执行风险", "政策监管", "成本资源"} else "opportunity"
            primary = next((marker for marker in markers if marker.lower() in merged.lower()), category)
            factors.append(
                {
                    "name": category,
                    "category": category,
                    "score": round(min(1.0, 0.28 + score * 0.09), 2),
                    "direction": direction,
                    "evidence": find_evidence_sentence(text, str(primary)),
                }
            )

    for term in extract_terms(merged, limit=10):
        if not any(term in str(factor["evidence"]) or term == factor["name"] for factor in factors):
            factors.append(
                {
                    "name": term,
                    "category": "材料高频信号",
                    "score": round(0.36 + min(merged.count(term), 8) * 0.05, 2),
                    "direction": "neutral",
                    "evidence": find_evidence_sentence(text, term),
                }
            )
        if len(factors) >= 10:
            break
    return factors[:10]


def find_evidence_sentence(text: str, keyword: str) -> str:
    if not keyword:
        return ""
    for sentence in split_sentences(text)[:120]:
        if keyword.lower() in sentence.lower():
            return sentence[:180]
    return split_sentences(text)[0][:180] if split_sentences(text) else text[:180]
