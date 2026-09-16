"""多源文献采集：arXiv、PubMed(E-utilities)、通用 RSS/Atom。

输出统一的 paper 字典结构:
    {
      "id": "arxiv:2509.01234",          # 跨源去重主键
      "source": "arXiv:cs.CL",
      "title": "...",
      "authors": ["Zhang San", "Li Si"],
      "url": "https://arxiv.org/abs/...",
      "pdf": "https://arxiv.org/pdf/...",
      "abstract": "...",
      "published": "2026-09-15",        # ISO 日期字符串, 未知为 ""
      "categories": ["cs.CL"],
      "rule": {keywords_any/all/exclude, authors}  # 供 processing 模块过滤
    }
"""
from __future__ import annotations

import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import feedparser
import requests

UTC = timezone.utc
HTTP_TIMEOUT = 25
USER_AGENT = "lit-push/1.0 (personal literature alert; contact: local)"

# 知网 RSS 官方域名在境外（GitHub Actions 海外 runner）会被 CDN 按地域拦截（418/证书异常）。
# 部署在国内的云函数中继可解决：把 CNKI_RSS_BASE 设为中继地址（如 https://xxx.tencentscf.com），
# 知网 feed 的请求会自动改走中继；不设置时直连官方域名（国内本地运行无需配置）。
CNKI_RSS_BASE = (os.environ.get("CNKI_RSS_BASE", "") or "").rstrip("/")


def _maybe_relay(url: str) -> str:
    """知网 RSS 链接按需替换为国内中继地址，其他源原样返回。"""
    if CNKI_RSS_BASE and "rss.cnki.net" in url:
        return re.sub(r"https?://rss\.cnki\.net", CNKI_RSS_BASE, url)
    return url


def _get(url: str, params: Optional[Dict[str, Any]] = None, tries: int = 3, timeout: int = HTTP_TIMEOUT):
    """带退避重试的 GET，应对瞬时连接重置/限流。"""
    last_exc: Optional[Exception] = None
    for attempt in range(tries):
        try:
            resp = requests.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < tries - 1:
                wait = 2 * (attempt + 1)
                resp = getattr(exc, "response", None)
                if resp is not None and getattr(resp, "status_code", 0) == 429:
                    wait = 10 * (attempt + 1)   # 限流时加长退避
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _rule_from(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "keywords_any": cfg.get("keywords_any", []) or [],
        "keywords_all": cfg.get("keywords_all", []) or [],
        "keywords_exclude": cfg.get("keywords_exclude", []) or [],
        "authors": cfg.get("authors", []) or [],
    }


def _parse_dt(value: str) -> Optional[datetime]:
    """兼容完整 ISO 时间、YYYY-MM-DD、YYYY-MM、YYYY；解析失败返回 None。"""
    if not value:
        return None
    text = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _within_lookback(pub_dt: Optional[datetime], days: int) -> bool:
    """按完整时间戳判断；无可用日期时不过滤（保留）。"""
    if pub_dt is None or not days:
        return True
    return pub_dt >= datetime.now(UTC) - timedelta(days=days)


# ---------------------------------------------------------------- arXiv
def _arxiv_keyword_term(keyword: str) -> str:
    k = keyword.strip()
    return f'(ti:"{k}" OR abs:"{k}")'


def _build_arxiv_query(cfg: Dict[str, Any]) -> str:
    clauses: List[str] = []
    cats = [c.strip() for c in (cfg.get("categories", []) or []) if c.strip()]
    if cats:
        clauses.append("(" + " OR ".join(f"cat:{c}" for c in cats) + ")")

    any_kw = [k for k in (cfg.get("keywords_any", []) or []) if k.strip()]
    if any_kw:
        clauses.append("(" + " OR ".join(_arxiv_keyword_term(k) for k in any_kw) + ")")
    for k in cfg.get("keywords_all", []) or []:
        if k.strip():
            clauses.append(_arxiv_keyword_term(k.strip()))

    if not clauses:
        # 无关键词时退化为按分类拉取最新
        if not cats:
            return "all:*"
        return " AND ".join(clauses) if clauses else "all:*"
    return " AND ".join(clauses)


def fetch_arxiv(cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    query = _build_arxiv_query(cfg)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": int(cfg.get("max_results", 80)),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    log.info("[arXiv] 请求: %s", url)
    resp = _get(url)
    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"arXiv 返回解析失败: {feed.bozo_exception}")

    rule = _rule_from(cfg)
    days = int(cfg.get("lookback_days", 2) or 2)
    papers: List[Dict[str, Any]] = []
    for e in feed.entries:
        raw_id = getattr(e, "id", "")
        m = re.search(r"abs/([^v\s]+)(v\d+)?$", raw_id)
        short_id = m.group(1) if m else raw_id
        pub_dt = None
        if getattr(e, "published_parsed", None):
            pub_dt = datetime(*e.published_parsed[:6], tzinfo=UTC)
        if not _within_lookback(pub_dt, days):
            continue

        pdf_url = ""
        for link in getattr(e, "links", []):
            if link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")
                break
        papers.append(
            {
                "id": f"arxiv:{short_id}",
                "source": "arXiv",
                "title": re.sub(r"\s+", " ", getattr(e, "title", "")).strip(),
                "authors": [a.get("name", "") for a in getattr(e, "authors", [])],
                "url": raw_id,
                "pdf": pdf_url,
                "abstract": re.sub(r"\s+", " ", getattr(e, "summary", "")).strip(),
                "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
                "pub_dt": pub_dt,
                "categories": [t.get("term", "") for t in getattr(e, "tags", [])],
                "rule": rule,
            }
        )
    log.info("[arXiv] 命中 %d 篇（时间窗 %d 天）", len(papers), days)
    return papers


# ---------------------------------------------------------------- PubMed
def fetch_pubmed(cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    term = (cfg.get("term") or "").strip()
    if not term:
        log.warning("[PubMed] 未配置 term, 跳过")
        return []
    api_key = None
    key_env = cfg.get("api_key_env")
    if key_env:
        import os

        api_key = os.environ.get(key_env)
    days = int(cfg.get("lookback_days", 3) or 3)

    search_params = {
        "db": "pubmed",
        "term": term,
        "retmax": int(cfg.get("max_results", 40)),
        "retmode": "json",
        "datetype": "edat",
        "reldate": days,
        "sort": "date",
    }
    if api_key:
        search_params["api_key"] = api_key
    log.info("[PubMed] 检索: %s", term)
    r = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=search_params)
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        log.info("[PubMed] 无结果")
        return []
    time.sleep(0.4 if not api_key else 0.12)  # 尊重限流: 3/s(无Key), 10/s(有Key)

    fetch_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
    if api_key:
        fetch_params["api_key"] = api_key
    r2 = _get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=fetch_params)
    return _parse_pubmed_xml(r2.content, rule=_rule_from(cfg), log=log)


def _text_of(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _parse_pubmed_xml(content: bytes, rule: Dict[str, Any], log) -> List[Dict[str, Any]]:
    root = ET.fromstring(content)
    papers: List[Dict[str, Any]] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text_of(art.find(".//PMID"))
        article = art.find(".//Article")
        if article is None:
            continue
        title = _text_of(article.find(".//ArticleTitle"))

        abstract_parts = []
        for ab in article.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            text = re.sub(r"\s+", " ", _text_of(ab))
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts)

        authors = []
        for au in article.findall(".//AuthorList/Author"):
            last, fore = _text_of(au.find("LastName")), _text_of(au.find("ForeName"))
            name = f"{fore} {last}".strip() or _text_of(au.find("CollectiveName"))
            if name:
                authors.append(name)

        journal = _text_of(article.find(".//Journal/Title"))
        year = _text_of(art.find(".//PubDate/Year")) or _text_of(art.find(".//PubDate/MedlineDate"))[:4]
        month = _text_of(art.find(".//PubDate/Month"))
        published = year
        if month and re.fullmatch(r"\d{1,2}", month):
            published = f"{year}-{int(month):02d}"
        elif month:
            published = year  # 非数字月份保持年仅
        cats = [c.get("UI", c.text or "") for c in article.findall(".//PublicationTypeList/PublicationType")]

        papers.append(
            {
                "id": f"pubmed:{pmid}",
                "source": f"PubMed{f' · {journal}' if journal else ''}",
                "title": re.sub(r"\s+", " ", title),
                "authors": authors,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pdf": "",
                "abstract": re.sub(r"\s+", " ", abstract),
                "published": published,
                "pub_dt": _parse_dt(published),
                "categories": cats,
                "rule": rule,
            }
        )
    log.info("[PubMed] 解析得到 %d 篇", len(papers))
    return papers


# ---------------------------------------------------------------- RSS
def fetch_rss(cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    papers: List[Dict[str, Any]] = []
    for feed_cfg in cfg.get("feeds", []) or []:
        if not feed_cfg.get("url"):
            continue
        name = feed_cfg.get("name", feed_cfg["url"])
        try:
            resp = _get(_maybe_relay(feed_cfg["url"]))
            feed = feedparser.parse(resp.content)
            rule = _rule_from(feed_cfg)
            days = int(feed_cfg.get("lookback_days", 7) or 7)
            count_before = len(papers)
            for e in feed.entries:
                pub_dt = None
                if getattr(e, "published_parsed", None):
                    pub_dt = datetime(*e.published_parsed[:6], tzinfo=UTC)
                elif getattr(e, "updated_parsed", None):
                    pub_dt = datetime(*e.updated_parsed[:6], tzinfo=UTC)
                if not _within_lookback(pub_dt, days):
                    continue
                summary = re.sub(r"<[^>]+>", " ", getattr(e, "summary", ""))
                link = getattr(e, "link", "")
                title_norm = re.sub(r"\s+", " ", getattr(e, "title", "")).strip()
                # 用“订阅名+归一化标题”做主键：知网等链接含动态 token，直接用 link 会破坏去重
                rss_id = f"rss:{name}:{_norm_title(title_norm)}"
                papers.append(
                    {
                        "id": rss_id,
                        "source": f"RSS · {name}",
                        "title": re.sub(r"\s+", " ", getattr(e, "title", "")).strip(),
                        "authors": [a.get("name", "") for a in getattr(e, "authors", [])],
                        "url": link,
                        "pdf": "",
                        "abstract": re.sub(r"\s+", " ", summary).strip(),
                        "published": pub_dt.strftime("%Y-%m-%d") if pub_dt else "",
                        "pub_dt": pub_dt,
                        "categories": [t.get("term", "") for t in getattr(e, "tags", [])],
                        "rule": rule,
                    }
                )
            log.info("[RSS] %s: %d 条", name, len(papers) - count_before)
        except Exception as exc:  # 单个订阅失败不影响整体
            log.warning("[RSS] %s 抓取失败: %s", name, exc)
    return papers


# ---------------------------------------------------------------- OpenAlex
def _reconstruct_abstract(inverted: Optional[Dict[str, List[int]]]) -> str:
    """OpenAlex 摘要以倒排索引返回，按位置还原为文本。"""
    if not inverted:
        return ""
    positions: Dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _oa_work_to_paper(w: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    loc = w.get("primary_location") or {}
    source = (loc.get("source") or {}).get("display_name", "")
    oa_loc = w.get("best_oa_location") or {}
    date_str = w.get("publication_date") or ""
    return {
        "id": "openalex:" + (w.get("id", "").rsplit("/", 1)[-1] or w.get("doi", "")),
        "source": f"OpenAlex · {source}" if source else "OpenAlex",
        "title": re.sub(r"\s+", " ", w.get("title") or "").strip(),
        "authors": [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])],
        "url": w.get("doi") or loc.get("landing_page_url") or w.get("id", ""),
        "pdf": oa_loc.get("pdf_url", "") or loc.get("pdf_url", ""),
        "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
        "published": date_str,
        "pub_dt": _parse_dt(date_str),
        "categories": [source, w.get("language", "")],
        "rule": rule,
    }


def fetch_openalex(cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    """OpenAlex：① terms 跨刊 OR 检索（英文/中文各一次）；② journal_sources 按 source id 锁刊。

    术语在服务端 OR 合并（短语加双引号），本地再用 rule 复筛降噪。免费、无需 Key。
    """
    per_page = int(cfg.get("per_page", 100))
    mailto = (cfg.get("mailto") or "").strip()
    papers: List[Dict[str, Any]] = []

    # ① 跨刊关键词检索
    en_terms = [q for q in (cfg.get("terms", []) or cfg.get("queries", [])) if q.strip()]
    zh_terms = [q for q in (cfg.get("terms_zh", []) or []) if q.strip()]
    days = int(cfg.get("lookback_days", 7) or 7)
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    base_filters = [f"from_publication_date:{since}", "type:article"]
    if cfg.get("journal_only", True):
        base_filters.append("primary_location.source.type:journal")

    for lang, terms in (("en", en_terms), ("zh", zh_terms)):
        if not terms:
            continue
        filters = base_filters + [f"language:{lang}"]
        params = {"search": " OR ".join(f'"{t.strip()}"' for t in terms),
                  "filter": ",".join(filters), "sort": "publication_date:desc",
                  "per-page": per_page}
        if mailto:
            params["mailto"] = mailto
        try:
            resp = _get("https://api.openalex.org/works", params=params, tries=3)
            results = resp.json().get("results", [])
        except Exception as exc:
            log.warning("[OpenAlex] %s 跨刊检索失败: %s", lang, exc)
            results = []
        rule = _rule_from({**cfg, "keywords_any": en_terms + zh_terms})
        papers.extend(_oa_work_to_paper(w, rule) for w in results)
        log.info("[OpenAlex] 跨刊检索（%s）%d 个术语，返回 %d 条", lang, len(terms), len(results))
        time.sleep(0.5)

    # ② 按 source id 锁定期刊目录（窗口更长，避免月刊/季刊漏期）
    j_days = int(cfg.get("journal_lookback_days", 21) or 21)
    j_since = (datetime.now(UTC) - timedelta(days=j_days)).strftime("%Y-%m-%d")
    for jspec in cfg.get("journal_sources", []) or []:
        sid = (jspec.get("source_id") or "").strip()
        if not sid:
            continue
        params = {"filter": (f"primary_location.source.id:{sid},"
                             f"from_publication_date:{j_since},type:article"),
                  "sort": "publication_date:desc", "per-page": per_page}
        if mailto:
            params["mailto"] = mailto
        try:
            resp = _get("https://api.openalex.org/works", params=params, tries=3)
            results = resp.json().get("results", [])
        except Exception as exc:
            log.warning("[OpenAlex] 锁刊 %s 失败: %s", jspec.get("name", sid), exc)
            continue
        rule = _rule_from(jspec)
        papers.extend(_oa_work_to_paper(w, rule) for w in results)
        log.info("[OpenAlex] 锁刊 %s：%d 篇", jspec.get("name", sid), len(results))
        time.sleep(0.4)

    if not en_terms and not zh_terms and not (cfg.get("journal_sources")):
        log.warning("[OpenAlex] 未配置 terms / terms_zh / journal_sources，跳过")
    return papers


# ---------------------------------------------------------------- Crossref
def _crossref_date(item: Dict[str, Any]):
    for key in ("published-print", "published-online", "published", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            p = parts[0]
            try:
                if len(p) >= 3:
                    dt = datetime(p[0], p[1], p[2], tzinfo=UTC)
                elif len(p) == 2:
                    dt = datetime(p[0], p[1], 1, tzinfo=UTC)
                else:
                    dt = datetime(p[0], 1, 1, tzinfo=UTC)
                label = dt.strftime("%Y-%m-%d") if len(p) >= 3 else (
                    dt.strftime("%Y-%m") if len(p) == 2 else dt.strftime("%Y")
                )
                return dt, label
            except (ValueError, TypeError):
                continue
    return None, ""


def fetch_crossref(cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    """按期刊 ISSN 订阅最新目录（Crossref），适合锁定人文社科核心期刊。"""
    journals = cfg.get("journals", []) or []
    if not journals:
        log.warning("[Crossref] 未配置 journals, 跳过")
        return []
    days = int(cfg.get("lookback_days", 21) or 21)
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = int(cfg.get("rows", 30))
    mailto = (cfg.get("mailto") or "").strip()
    papers: List[Dict[str, Any]] = []

    for j in journals:
        issn = (j.get("issn") or "").strip()
        name = j.get("name", issn)
        if not issn:
            continue
        params = {
            "rows": rows,
            "sort": "published",
            "order": "desc",
            "filter": f"from-pub-date:{since},type:journal-article",
        }
        if mailto:
            params["mailto"] = mailto
        try:
            resp = _get(f"https://api.crossref.org/journals/{issn}/works", params=params)
            items = resp.json().get("message", {}).get("items", [])
            n0 = len(papers)
            rule = _rule_from(j)
            for item in items:
                pub_dt, date_label = _crossref_date(item)
                if pub_dt and pub_dt < datetime.now(UTC) - timedelta(days=days):
                    continue
                doi = item.get("DOI", "")
                authors = [
                    " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x).strip()
                    for a in item.get("author", [])
                ]
                abstract = re.sub(r"<[^>]+>", " ", item.get("abstract", ""))
                papers.append(
                    {
                        "id": f"doi:{doi.lower()}" if doi else f"crossref:{item.get('URL','')}",
                        "source": f"期刊 · {name}",
                        "title": re.sub(r"\s+", " ", (item.get("title") or [""])[0]).strip(),
                        "authors": authors,
                        "url": f"https://doi.org/{doi}" if doi else item.get("URL", ""),
                        "pdf": "",
                        "abstract": re.sub(r"\s+", " ", abstract).strip(),
                        "published": date_label,
                        "pub_dt": pub_dt,
                        "categories": [c for c in (item.get("container-title") or [])[:1]],
                        "rule": rule,
                    }
                )
            log.info("[Crossref] %s: %d 篇", name, len(papers) - n0)
        except Exception as exc:
            log.warning("[Crossref] %s 拉取失败: %s", name, exc)
        time.sleep(float(cfg.get("polite_interval", 0.8)))
    return papers


# ---------------------------------------------------------------- 汇总
def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", title.lower())


def collect_all(cfg: Dict[str, Any], log) -> List[Dict[str, Any]]:
    """采集所有启用的数据源，并做跨源粗去重。"""
    src = cfg.get("sources", {}) or {}
    collected: List[Dict[str, Any]] = []

    if src.get("arxiv", {}).get("enabled"):
        try:
            collected += fetch_arxiv(src["arxiv"], log)
        except Exception as exc:
            log.warning("arXiv 采集失败: %s", exc)
    if src.get("pubmed", {}).get("enabled"):
        try:
            collected += fetch_pubmed(src["pubmed"], log)
        except Exception as exc:
            log.warning("PubMed 采集失败: %s", exc)
    if src.get("rss", {}).get("enabled"):
        try:
            collected += fetch_rss(src["rss"], log)
        except Exception as exc:
            log.warning("RSS 采集失败: %s", exc)
    if src.get("openalex", {}).get("enabled"):
        try:
            collected += fetch_openalex(src["openalex"], log)
        except Exception as exc:
            log.warning("OpenAlex 采集失败: %s", exc)
    if src.get("crossref", {}).get("enabled"):
        try:
            collected += fetch_crossref(src["crossref"], log)
        except Exception as exc:
            log.warning("Crossref 采集失败: %s", exc)

    # 跨源去重：同 id 或归一化标题相同，保留摘要更长的一条
    merged: Dict[str, Dict[str, Any]] = {}
    for p in collected:
        key = p["id"]
        title_key = "title:" + _norm_title(p["title"])
        existing = merged.get(key) or merged.get(title_key)
        if existing is None:
            merged[key] = p
            if title_key not in merged:
                merged[title_key] = p
        elif len(p.get("abstract", "")) > len(existing.get("abstract", "")):
            existing.update(p)
    deduped = [v for k, v in merged.items() if not k.startswith("title:")]
    log.info("采集合计 %d 篇，跨源去重后 %d 篇", len(collected), len(deduped))
    return deduped
