# -*- coding: utf-8 -*-
"""筛选、去重、LLM 深度提炼与排序。"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests


# ---------------------------------------------------------------- 关键词匹配
def keyword_hit(text: str, keyword: str) -> bool:
    """英文按词边界匹配（避免 translation 命中 translational），中文按子串匹配。"""
    if not text or not keyword:
        return False
    if re.search(r"[A-Za-z]", keyword):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(keyword.lower()) + r"(?![A-Za-z0-9])"
        return re.search(pattern, text.lower()) is not None
    return keyword in text


# 期刊 RSS/Crossref 中混入的非研究论文条目（稿约、征稿、启事、栏目页、会议新闻等）
NON_ARTICLE_PATTERNS = [
    r"稿约", r"征稿(启事|通知|简则)?", r"投稿(须知|指南|要求)", r"撰稿须知", r"写作须知",
    r"格式(要求|规范)", r"参考文献著录", r"征订", r"欢迎(订阅|投稿)", r"订阅办法",
    r"^启事", r"声明$", r"编者按", r"主持人语", r"本期导读", r"^导读$", r"目次", r"^目录$",
    r"封面", r"封[二三四]", r"会讯", r"会议(通知|预告)", r"研讨会(通知|预告)",
    r"书讯", r"讣告", r"逝世", r"^更正", r"通知$",
    r"^.{0,16}专题$",                                   # “译者行为研究”专题 等栏目条目
    r"(在|于).{2,14}(举行|召开|落幕|开幕)$",            # 会议新闻
    r"(当选|受聘|荣获|聘任).{0,16}(主席|会长|教授|院士|主任|称号|理事长)",
    r"(习近平|总书记|国家主席|国务院总理).{0,24}(指示|讲话|强调|贺信|致辞)",
    r"》(出版|发行)$",                                   # 书讯
    r"\bcall for (papers|abstracts|submissions)\b",
    r"\bfront matter\b", r"\bback matter\b",
    r"\btable of contents\b", r"\berrat(um|a)\b",
    r"\backnowledg(e)?ments? of reviewers\b",
    r"\beditorial board\b",
]
_NON_ARTICLE_RE = re.compile("|".join(f"(?:{p})" for p in NON_ARTICLE_PATTERNS), re.IGNORECASE)


def is_non_article(title: str) -> bool:
    return bool(title and _NON_ARTICLE_RE.search(title.strip()))


def match_paper(paper: Dict[str, Any], rule: Dict[str, Any]) -> bool:
    """按该数据源附带的 rule 做本地复筛。"""
    if is_non_article(paper.get("title", "")):
        return False
    text = f"{paper.get('title', '')}\n{paper.get('abstract', '')}"
    excludes = rule.get("keywords_exclude", []) or []
    if any(keyword_hit(text, kw) for kw in excludes):
        return False
    any_kw = [k for k in (rule.get("keywords_any", []) or []) if k.strip()]
    if any_kw and not any(keyword_hit(text, kw) for kw in any_kw):
        return False
    all_kw = [k for k in (rule.get("keywords_all", []) or []) if k.strip()]
    if all_kw and not all(keyword_hit(text, kw) for kw in all_kw):
        return False
    authors_rule = [a for a in (rule.get("authors", []) or []) if a.strip()]
    if authors_rule:
        authors = " ".join(paper.get("authors", []) or [])
        if not any(a.lower() in authors.lower() for a in authors_rule):
            return False
    return True


def filter_papers(papers: List[Dict[str, Any]], cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    kept = [p for p in papers if match_paper(p, p.get("rule", {}))]
    dropped = len(papers) - len(kept)
    log.info("关键词复筛保留 %d 篇（滤除 %d 篇）", len(kept), dropped)
    return kept


# ---------------------------------------------------------------- 去重存储
def _seen_path(cfg: Dict[str, Any]) -> str:
    return (cfg.get("storage", {}) or {}).get("seen_file", "data/seen.json")


def load_seen(path: str) -> Dict[str, str]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def dedup_new(papers: List[Dict[str, Any]], cfg: Dict[str, Any], log):
    seen = load_seen(_seen_path(cfg))
    new = [p for p in papers if p.get("id") not in seen]
    log.info("与历史记录去重后，本次新增 %d 篇（已推过 %d 篇）", len(new), len(seen))
    return new, seen


def save_seen(seen: Dict[str, str], papers: List[Dict[str, Any]], cfg: Dict[str, Any]) -> None:
    path = _seen_path(cfg)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    for p in papers:
        seen[p["id"]] = today
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- LLM 深度提炼
def _build_prompt(batch: List[Dict[str, Any]], category_names: List[str], other_name: str) -> str:
    lines = [
        "你是翻译学与传播学领域的资深文献综述专家。请对以下论文逐篇完成：",
        "1) 归类：category 必须严格从下列类别中选一个：" + "；".join(category_names[:-1])
        + f"；都不符合才选“{other_name}”。",
        "2) sub_topic：用 6-14 个字概括具体研究方向（如“区域翻译史”“医学口译教学”"
        "“大模型译后编辑”“对外传播话语”）。",
        "3) keywords：3-5 个中文学术关键词数组。",
        "4) summary_zh：80-150 字中文摘要，覆盖研究问题、方法、发现。",
        "5) core_arguments：2-3 句，讲清核心观点与论证脉络。",
        "6) valuable_points：1-2 句，指出对“语言智能翻译与传播”方向研究者最有参考价值之处。",
        "7) future_trends：1-2 句，指出该文揭示的、未来可深入的研究趋向。",
        "8) innovations：1-2 句，提出可在此基础上延伸的具体创新点（新问题/新材料/新方法）。",
        "9) score：0-10 的相关度与质量综合分；recommend 为 true/false（7 分及以上为 true）。",
        "只输出 JSON："
        '{"papers":[{"id":"1","category":"...","sub_topic":"...","keywords":[...],'
        '"summary_zh":"...","core_arguments":"...","valuable_points":"...",'
        '"future_trends":"...","innovations":"...","score":8,"recommend":true}]}',
        "",
    ]
    for i, p in enumerate(batch, 1):
        lines.append(f"[{i}] 标题: {p.get('title', '')}")
        lines.append(f"    来源: {p.get('source', '')}")
        abstract = (p.get("abstract") or "").replace("\n", " ")
        lines.append(f"    摘要: {abstract[:1500]}")
        lines.append("")
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def enrich_with_llm(papers: List[Dict[str, Any]], cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    """逐批调用 LLM 完成归类与深度提炼；未配置/失败时由规则分类兜底。"""
    llm = cfg.get("llm", {}) or {}
    if not llm.get("enabled") or not papers:
        return papers
    api_key = os.getenv(llm.get("api_key_env", "LLM_API_KEY"), "")
    if not api_key:
        log.warning("未检测到 LLM API Key，跳过 AI 提炼（规则分类 + 原文摘要）")
        return papers

    from litpush.classify import category_names
    names = category_names(cfg)
    other_name = names[-1]
    batch_size = int(llm.get("batch_size", 8))
    max_chars = int(llm.get("max_abstract_chars", 1800))
    for p in papers:
        if p.get("abstract"):
            p["abstract"] = p["abstract"][:max_chars]

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = llm["base_url"].rstrip("/") + "/chat/completions"

    for start in range(0, len(papers), batch_size):
        batch = papers[start:start + batch_size]
        prompt = _build_prompt(batch, names, other_name)
        body = {
            "model": llm.get("model", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = _parse_response(content)
            items = {str(x.get("id")): x for x in parsed.get("papers", [])}
            for i, p in enumerate(batch, 1):
                info = items.get(str(i))
                if not info:
                    continue
                cat = (info.get("category") or "").strip()
                if cat in names:
                    p["category"] = cat
                sub = (info.get("sub_topic") or "").strip()
                if sub:
                    p["sub_topic"] = sub
                kws = info.get("keywords")
                if isinstance(kws, list) and kws:
                    p["keywords_zh"] = [str(k).strip() for k in kws if str(k).strip()]
                for field in ("summary_zh", "core_arguments", "valuable_points",
                              "future_trends", "innovations"):
                    val = info.get(field)
                    if isinstance(val, str) and val.strip():
                        p[field] = val.strip()
                try:
                    p["score"] = float(info.get("score", 0))
                except (TypeError, ValueError):
                    p["score"] = 0
                p["recommend"] = bool(info.get("recommend", p.get("score", 0) >= 7))
                p["llm_enriched"] = True
            log.info("AI 提炼批次 %d 完成（%d 篇）", start // batch_size + 1, len(batch))
        except Exception as exc:
            log.warning("AI 提炼批次 %d 失败：%s，该批使用降级内容", start // batch_size + 1, exc)
        time.sleep(1)

    if llm.get("only_recommended"):
        before = len(papers)
        papers = [p for p in papers if p.get("recommend", True)]
        log.info("only_recommended 过滤：%d -> %d 篇", before, len(papers))
    return papers


# ---------------------------------------------------------------- 排序
def rank_papers(papers: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """有 LLM 评分按评分；否则按发表时间倒序。"""
    def key(p):
        score = p.get("score")
        return (score is not None, score if score is not None else 0,
                p.get("pub_dt") is not None,
                p.get("pub_dt").timestamp() if p.get("pub_dt") else 0)
    papers.sort(key=key, reverse=True)
    return papers
