# -*- coding: utf-8 -*-
"""报告渲染、归档与多渠道推送（飞书分类卡片 / 邮件 / Telegram / PushPlus）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import smtplib
import time
from collections import OrderedDict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

import requests

from litpush.classify import group_papers

FEISHU_CARD_LIMIT = 15
FEISHU_CARD_MAX_CHARS = 26000
HEADER_COLORS = {"一": "blue", "二": "turquoise", "三": "orange",
                 "四": "green", "五": "grey"}


def _venue(p: Dict[str, Any]) -> str:
    s = p.get("source", "") or ""
    for pre in ("期刊 · ", "OpenAlex · ", "RSS · ", "PubMed · "):
        if s.startswith(pre):
            return s[len(pre):]
    return s


def _authors(p: Dict[str, Any], limit: int = 3) -> str:
    authors = p.get("authors") or []
    if len(authors) > limit:
        return ", ".join(authors[:limit]) + " et al."
    return ", ".join(authors)


def _short(text: str, n: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


# ================================================================ Markdown
def render_paper_md(i: int, p: Dict[str, Any]) -> str:
    url = p.get("url") or ""
    title = p.get("title", "(untitled)")
    head = f"### {i}. [{title}]({url})\n" if url else f"### {i}. {title}\n"
    meta = "｜".join(m for m in (_venue(p), _authors(p), p.get("published", "")) if m)
    lines = [head, f"- **来源**：{meta}"]
    if p.get("score") is not None:
        lines.append(f"- **相关度评分**：{p['score']:.1f}/10"
                     + ("（推荐）" if p.get("recommend") else ""))
    if p.get("sub_topic"):
        lines.append(f"- **研究方向**：{p['sub_topic']}")
    if p.get("keywords_zh"):
        lines.append(f"- **关键词**：{'、'.join(p['keywords_zh'])}")
    for label, field in (("中文摘要", "summary_zh"), ("核心观点与脉络", "core_arguments"),
                         ("参考价值", "valuable_points"), ("未来研究趋向", "future_trends"),
                         ("可延伸创新点", "innovations")):
        if p.get(field):
            lines.append(f"- **{label}**：{p[field]}")
    if not p.get("summary_zh") and p.get("abstract"):
        lines.append(f"- **原文摘要**：{_short(p['abstract'], 600)}")
    lines.append("")
    return "\n".join(lines)


def render_markdown(groups: "OrderedDict[str, list]", total: int) -> str:
    counts = "　".join(f"{k} {len(v)} 篇" for k, v in groups.items())
    lines = ["# 文献推送日报", "",
             f"> 本期共 **{total}** 篇新文献　|　{counts}",
             "> 数据来源：arXiv · OpenAlex · Crossref 期刊目录 · 知网期刊 RSS", ""]
    for cat, items in groups.items():
        lines.append(f"\n## {cat}（{len(items)} 篇）\n")
        if not items:
            lines.append("_本期无_")
            continue
        for i, p in enumerate(items, 1):
            lines.append(render_paper_md(i, p))

    deep = [p for items in groups.values() for p in items
            if p.get("future_trends") or p.get("innovations")]
    if deep:
        lines.append("\n---\n")
        lines.append("# 专题汇编：未来研究方向与可延伸创新点\n")
        lines.append("> 由 LLM 逐篇提炼，便于集中选题与开题参考。\n")
        for p in deep:
            title = p.get("title", "(untitled)")
            url = p.get("url") or ""
            lines.append(f"## [{title}]({url})" if url else f"## {title}")
            tag = "｜".join(t for t in (p.get("category", ""), p.get("sub_topic", "")) if t)
            if tag:
                lines.append(f"**{tag}**\n")
            if p.get("future_trends"):
                lines.append(f"- **未来研究趋向**：{p['future_trends']}")
            if p.get("innovations"):
                lines.append(f"- **可延伸创新点**：{p['innovations']}")
            lines.append("")
    return "\n".join(lines)


# ================================================================ HTML
def render_paper_html(i: int, p: Dict[str, Any]) -> str:
    url = p.get("url") or "#"
    meta = "　·　".join(m for m in (_venue(p), _authors(p), p.get("published", "")) if m)
    rows = []
    if p.get("score") is not None:
        rows.append(f"<span class='score'>评分 {p['score']:.1f}/10"
                    + ("（推荐）" if p.get("recommend") else "") + "</span>")
    if p.get("sub_topic"):
        rows.append(f"<span class='tag'>{p['sub_topic']}</span>")
    if p.get("keywords_zh"):
        rows.append(f"<div class='kw'>关键词：{'、'.join(p['keywords_zh'])}</div>")
    for label, field in (("中文摘要", "summary_zh"), ("核心观点与脉络", "core_arguments"),
                         ("参考价值", "valuable_points"), ("未来研究趋向", "future_trends"),
                         ("可延伸创新点", "innovations")):
        if p.get(field):
            rows.append(f"<p><b>{label}：</b>{p[field]}</p>")
    if not p.get("summary_zh") and p.get("abstract"):
        rows.append(f"<p><b>原文摘要：</b>{_short(p['abstract'], 500)}</p>")
    return f"""<div class="paper">
  <div class="p-title">{i}. <a href="{url}">{p.get('title', '(untitled)')}</a></div>
  <div class="meta">{meta}</div>{''.join(rows)}
</div>"""


def render_html(groups: "OrderedDict[str, list]", total: int, today: str) -> str:
    counts = "　".join(f"{k}：{len(v)}" for k, v in groups.items())
    sections = []
    for cat, items in groups.items():
        body = "".join(render_paper_html(i, p) for i, p in enumerate(items, 1)) \
            if items else "<p style='color:#888'>本期无</p>"
        sections.append(f"<h2>{cat}（{len(items)} 篇）</h2>{body}")
    deep = [p for items in groups.values() for p in items
            if p.get("future_trends") or p.get("innovations")]
    if deep:
        rows = []
        for p in deep:
            tag = "｜".join(t for t in (p.get("category", ""), p.get("sub_topic", "")) if t)
            rows.append(
                f"<div class='paper'><div class='p-title'><a href='{p.get('url','#')}'>"
                f"{p.get('title', '')}</a></div><div class='meta'>{tag}</div>"
                + (f"<p><b>未来研究趋向：</b>{p['future_trends']}</p>" if p.get("future_trends") else "")
                + (f"<p><b>可延伸创新点：</b>{p['innovations']}</p>" if p.get("innovations") else "")
                + "</div>")
        sections.append("<h2 style='color:#2e7d4f'>专题汇编：未来研究方向与可延伸创新点</h2>"
                        + "".join(rows))
    return f"""<html><body style="font-family:'Segoe UI','Microsoft YaHei',Arial,sans-serif;
line-height:1.7;max-width:820px;margin:auto;color:#222;">
<h1 style="border-bottom:3px solid #4F6B9A;padding-bottom:8px;">文献推送日报 · {today}</h1>
<p>本期共 <b>{total}</b> 篇　|　{counts}</p>{''.join(sections)}
<hr><p style="color:#888;font-size:12px;">由 lit-push 自动生成 · arXiv / OpenAlex / Crossref / 知网期刊 RSS</p>
<style>.paper{{border:1px solid #e3e3e3;border-radius:8px;padding:12px 16px;margin:10px 0;}}
.p-title{{font-weight:bold;font-size:15px;}}.p-title a{{color:#1a4f8b;text-decoration:none;}}
.meta{{color:#888;font-size:12px;margin:4px 0 8px;}}
.tag{{display:inline-block;background:#eef2f8;border-radius:10px;padding:1px 10px;font-size:12px;margin-right:6px;}}
.score{{color:#2e7d4f;font-size:12px;margin-right:6px;}}.kw{{font-size:13px;color:#444;margin:4px 0;}}
</style></body></html>"""


# ================================================================ 纯文本
def render_paper_text(p: Dict[str, Any]) -> str:
    lines = [f"*{p.get('title', '(untitled)')}*",
             " | ".join(m for m in (_venue(p), p.get("published", "")) if m)]
    if p.get("sub_topic"):
        lines.append(f"方向：{p['sub_topic']}")
    if p.get("keywords_zh"):
        lines.append(f"关键词：{'、'.join(p['keywords_zh'])}")
    if p.get("summary_zh"):
        lines.append(_short(p["summary_zh"], 220))
    elif p.get("abstract"):
        lines.append(_short(p["abstract"], 220))
    if p.get("future_trends"):
        lines.append(f"趋向：{_short(p['future_trends'], 120)}")
    if p.get("url"):
        lines.append(p["url"])
    return "\n".join(lines)


def render_plain(groups: "OrderedDict[str, list]", total: int, today: str) -> str:
    counts = "　".join(f"{k} {len(v)}" for k, v in groups.items())
    blocks = [f"文献推送日报 {today}\n共 {total} 篇\n{counts}"]
    for cat, items in groups.items():
        if items:
            blocks.append(f"【{cat}｜{len(items)} 篇】\n\n"
                          + "\n\n".join(render_paper_text(p) for p in items))
    deep = [p for items in groups.values() for p in items
            if p.get("future_trends") or p.get("innovations")]
    if deep:
        body = "\n\n".join(
            f"*{p.get('title', '')}*\n趋向：{p.get('future_trends', '')}\n创新：{p.get('innovations', '')}"
            for p in deep)
        blocks.append("【未来研究方向与创新点汇编】\n\n" + body)
    return "\n\n——————\n\n".join(blocks)


def _chunks(text: str, limit: int = 3500) -> List[str]:
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > limit and cur:
            parts.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts


# ================================================================ 飞书卡片
def _feishu_sign(secret: str, ts: int) -> str:
    string_to_sign = f"{ts}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _card(title: str, template: str, elements: List[dict]) -> dict:
    return {"config": {"wide_screen_mode": True},
            "header": {"template": template,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": elements}


def _lark_paper(p: Dict[str, Any]) -> str:
    title = p.get("title", "(untitled)")
    url = p.get("url") or ""
    head = f"**[{title}]({url})**" if url else f"**{title}**"
    meta = " · ".join(m for m in (_venue(p), p.get("published", "")) if m)
    if p.get("score") is not None:
        meta += f" · ⭐{p['score']:.1f}"
    lines = [head]
    if meta:
        lines.append(meta)
    tags = "　".join(t for t in (p.get("sub_topic", ""),
                                 "、".join(p.get("keywords_zh", []))) if t)
    if tags:
        lines.append(tags)
    if p.get("summary_zh"):
        lines.append("📝 " + _short(p["summary_zh"], 260))
    elif p.get("abstract"):
        lines.append("📝 " + _short(p["abstract"], 260))
    if p.get("core_arguments"):
        lines.append("💡 " + _short(p["core_arguments"], 200))
    return "\n".join(lines)


FEISHU_BYTE_BUDGET = 22000   # 单卡正文 UTF-8 字节预算（飞书卡片整体上限 30KB）


def _paginate(blocks: List[str], budget: int = FEISHU_BYTE_BUDGET) -> List[List[str]]:
    """按 UTF-8 字节预算把 markdown 块切成多页，避免单卡超长被飞书拒绝。"""
    pages: List[List[str]] = []
    cur: List[str] = []
    cur_len = 0
    for content in blocks:
        size = len(content.encode("utf-8")) + 240  # div/hr/JSON 包装的保守开销
        if cur and cur_len + size > budget:
            pages.append(cur)
            cur, cur_len = [], 0
        cur.append(content)
        cur_len += size
    if cur:
        pages.append(cur)
    return pages or [[]]


def _blocks_to_elements(blocks: List[str]) -> List[dict]:
    elements = []
    for content in blocks:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})
        elements.append({"tag": "hr"})
    if elements:
        elements.pop()
    return elements


def build_feishu_cards(groups: "OrderedDict[str, list]", total: int,
                       today: str, cfg: Dict[str, Any]) -> List[dict]:
    if total == 0:
        return [_card(f"文献推送日报 · {today}", "grey",
                      [{"tag": "div", "text": {"tag": "lark_md",
                                               "content": "时间窗内没有检索到新文献。"}}])]
    max_per = int((cfg.get("delivery", {}).get("feishu", {}) or {}).get(
        "max_per_category", FEISHU_CARD_LIMIT))
    counts = "　".join(f"**{k}** {len(v)} 篇" for k, v in groups.items())
    cards = [_card(f"文献推送日报 · {today}（共 {total} 篇）", "blue", [
        {"tag": "div", "text": {"tag": "lark_md", "content": counts}},
        {"tag": "note", "elements": [{"tag": "plain_text",
                                      "content": "来源：arXiv · OpenAlex · Crossref · 知网RSS；完整日报见仓库 data/reports"}]},
    ])]
    for cat, items in groups.items():
        if not items:
            continue
        shown, rest = items[:max_per], items[max_per:]
        blocks = [_lark_paper(p) for p in shown]
        if rest:
            blocks.append(f"📎 另有 {len(rest)} 篇超出卡片展示上限，见仓库完整日报 data/reports")
        pages = _paginate(blocks)
        color = HEADER_COLORS.get((cat.strip()[:1] if cat else ""), "blue")
        for idx, page in enumerate(pages, 1):
            suffix = f"（{idx}/{len(pages)}）" if len(pages) > 1 else ""
            cards.append(_card(f"{cat}（{len(items)} 篇）{suffix}", color,
                               _blocks_to_elements(page)))

    deep = [p for items in groups.values() for p in items
            if p.get("future_trends") or p.get("innovations")]
    if deep:
        blocks = []
        for p in deep:
            title = p.get("title", "(untitled)")
            url = p.get("url") or ""
            block = (f"**[{title}]({url})**" if url else f"**{title}**")
            if p.get("sub_topic"):
                block += f"\n（{p['sub_topic']}）"
            if p.get("future_trends"):
                block += f"\n🔭 趋向：{_short(p['future_trends'], 180)}"
            if p.get("innovations"):
                block += f"\n🚀 创新：{_short(p['innovations'], 180)}"
            blocks.append(block)
        pages = _paginate(blocks)
        for idx, page in enumerate(pages, 1):
            suffix = f"（{idx}/{len(pages)}）" if len(pages) > 1 else ""
            cards.append(_card(f"未来研究方向与可延伸创新点汇编{suffix}", "green",
                               _blocks_to_elements(page)))
    return cards


def _post_feishu(card: dict, fs: Dict[str, Any], log, index: int = 1, total_cards: int = 1) -> None:
    webhook = os.getenv(fs.get("webhook_env", "FEISHU_WEBHOOK"), "")
    secret = os.getenv(fs.get("secret_env", "FEISHU_SECRET"), "")
    if not webhook:
        raise RuntimeError("未配置 FEISHU_WEBHOOK")
    body = {"msg_type": "interactive", "card": card}
    if secret:
        ts = int(time.time())
        body["timestamp"] = str(ts)
        body["sign"] = _feishu_sign(secret, ts)
    r = requests.post(webhook, json=body, timeout=20)
    data = r.json()
    if data.get("code", 0) != 0 and data.get("StatusCode", 0) != 0:
        raise RuntimeError(f"飞书返回错误：{data}")
    log.info("飞书卡片 %d/%d 发送成功", index, total_cards)
    time.sleep(0.5)


# ================================================================ 其他渠道
def _send_email(html: str, subject: str, cfg: Dict[str, Any], log) -> None:
    em = cfg["delivery"]["email"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = em.get("sender") or os.getenv(em["username_env"], "")
    msg["To"] = ", ".join(em["recipients"])
    msg.attach(MIMEText(html, "html", "utf-8"))
    if em.get("use_ssl", True):
        server = smtplib.SMTP_SSL(em["smtp_host"], em["smtp_port"], timeout=30)
    else:
        server = smtplib.SMTP(em["smtp_host"], em["smtp_port"], timeout=30)
        server.starttls()
    server.login(os.getenv(em["username_env"], ""), os.getenv(em["password_env"], ""))
    server.sendmail(msg["From"], em["recipients"], msg.as_string())
    server.quit()


def _send_telegram(text: str, cfg: Dict[str, Any], log) -> None:
    tg = cfg["delivery"]["telegram"]
    token, chat_id = os.getenv(tg["bot_token_env"], ""), os.getenv(tg["chat_id_env"], "")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunks(text):
        requests.post(url, json={"chat_id": chat_id, "text": chunk,
                                 "parse_mode": "Markdown", "disable_web_page_preview": True},
                      timeout=20)


def _send_pushplus(html: str, subject: str, cfg: Dict[str, Any], log) -> None:
    pp = cfg["delivery"]["pushplus"]
    body = {"token": os.getenv(pp["token_env"], ""), "title": subject,
            "content": html, "template": "html"}
    if pp.get("topic"):
        body["topic"] = pp["topic"]
    r = requests.post("https://www.pushplus.plus/send", json=body, timeout=20)
    if r.json().get("code") != 200:
        raise RuntimeError(f"PushPlus 返回：{r.text}")


# ================================================================ 主入口
def deliver(papers: List[Dict[str, Any]], today: str, cfg: Dict[str, Any], log) -> int:
    """渲染、归档并推送；返回成功送达的渠道数（0 表示全部失败）。"""
    groups = group_papers(papers, cfg)
    total = len(papers)
    md_report = render_markdown(groups, total)
    html_report = render_html(groups, total, today)
    plain_report = render_plain(groups, total, today)
    subject = f"文献推送日报 {today}（{total} 篇）"

    # 完整日报归档到仓库（Actions 会自动 commit）
    report_dir = (cfg.get("storage", {}) or {}).get("report_dir", "data/reports")
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, f"{today}.md"), "w", encoding="utf-8") as f:
        f.write(md_report)
    log.info("完整日报已归档：%s/%s.md", report_dir, today)

    if total == 0 and not cfg.get("empty_notify", True):
        log.info("今日无新增，且关闭了 empty_notify，不发送")
        return 1

    d = cfg.get("delivery", {}) or {}
    enabled = [name for name in ("feishu", "email", "telegram", "pushplus")
               if (d.get(name, {}) or {}).get("enabled")]
    if not enabled:
        log.warning("未启用任何推送渠道，报告仅保存在本地 %s", report_dir)
        return 1

    success = 0
    if d.get("feishu", {}).get("enabled"):
        try:
            cards = build_feishu_cards(groups, total, today, cfg)
            for i, card in enumerate(cards, 1):
                _post_feishu(card, d["feishu"], log, i, len(cards))
            success += 1
        except Exception as exc:
            log.error("飞书推送失败：%s", exc)
    if d.get("email", {}).get("enabled"):
        try:
            _send_email(html_report, subject, cfg, log)
            log.info("邮件推送成功")
            success += 1
        except Exception as exc:
            log.error("邮件推送失败：%s", exc)
    if d.get("telegram", {}).get("enabled"):
        try:
            _send_telegram(plain_report, cfg, log)
            log.info("Telegram 推送成功")
            success += 1
        except Exception as exc:
            log.error("Telegram 推送失败：%s", exc)
    if d.get("pushplus", {}).get("enabled"):
        try:
            _send_pushplus(html_report, subject, cfg, log)
            log.info("PushPlus 推送成功")
            success += 1
        except Exception as exc:
            log.error("PushPlus 推送失败：%s", exc)
    return success
