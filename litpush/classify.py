# -*- coding: utf-8 -*-
"""按四大研究板块自动归类。

- LLM 开启时：类别与具体研究方向（sub_topic）由模型给出，本模块只负责分组。
- LLM 未开启：用 config.classification 中的关键词规则打分兜底（英文词边界、中文子串）。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List

from litpush.processing import keyword_hit


def category_names(cfg: Dict[str, Any]) -> List[str]:
    """按配置顺序返回全部类别名（末尾为兜底的“其他相关”）。"""
    names = [c["name"] for c in cfg.get("classification", {}).get("categories", [])]
    other = cfg.get("classification", {}).get("fallback_other", "五、其他相关")
    if other not in names:
        names.append(other)
    return names


def _score_category(text: str, title: str, keywords: List[str]) -> int:
    score = 0
    for kw in keywords or []:
        if keyword_hit(text, kw):
            score += 2 if keyword_hit(title, kw) else 1
    return score


def rule_classify(paper: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    """规则兜底分类：两轮打分。

    第一轮用强特征词（keywords）；全部不中时，第二轮用弱信号词
    （weak_keywords，如 history / student / automatic / media 等语境词），
    避免把翻译专刊里的高相关论文一股脑归入“其他”。两轮都不中才归兜底类。
    """
    cls_cfg = cfg.get("classification", {})
    categories = cls_cfg.get("categories", [])
    other = cls_cfg.get("fallback_other", "五、其他相关")
    title = paper.get("title", "") or ""
    text = f"{title}\n{paper.get('abstract', '') or ''}"

    best_name, best_score = other, 0
    for cat in categories:
        score = _score_category(text, title, cat.get("keywords", []))
        if score > best_score:
            best_name, best_score = cat["name"], score
    if best_score > 0:
        return best_name

    # 第二轮：弱信号归类
    weak_name, weak_score = other, 0
    for cat in categories:
        score = _score_category(text, title, cat.get("weak_keywords", []))
        if score > weak_score:
            weak_name, weak_score = cat["name"], score
    return weak_name if weak_score > 0 else other


def apply_rule_classification(papers: List[Dict[str, Any]], cfg: Dict[str, Any]) -> None:
    """就地为缺少 category 的论文补类别（规则模式下 sub_topic 留空）。"""
    for p in papers:
        if not p.get("category"):
            p["category"] = rule_classify(p, cfg)
        if not p.get("sub_topic"):
            p["sub_topic"] = ""


def group_papers(papers: List[Dict[str, Any]], cfg: Dict[str, Any]) -> "OrderedDict[str, list]":
    """按类别分组，保持配置顺序；组内按 LLM 评分降序。"""
    names = category_names(cfg)
    groups: "OrderedDict[str, list]" = OrderedDict((n, []) for n in names)
    other = names[-1]
    for p in papers:
        cat = p.get("category") or other
        groups[cat if cat in groups else other].append(p)
    for items in groups.values():
        items.sort(key=lambda x: (x.get("score") is not None,
                                  x.get("score") if x.get("score") is not None else 0),
                   reverse=True)
    return groups
