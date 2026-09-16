# -*- coding: utf-8 -*-
"""知网期刊 RSS 国内中继 —— 腾讯云函数 SCF（Python 3.10，事件函数 + 函数 URL）。

背景：GitHub Actions 的 runner 在境外，直连 rss.cnki.net 会被知网 CDN 按地域拦截
（证书主机名不匹配 / HTTP 418）。本函数部署在国内区域（如广州/上海/北京），
代为请求知网官方 RSS 并原样返回 XML，Actions 通过函数 URL 访问即可。

安全：仅允许 /knavi/rss/<2-8 位字母数字> 路径，不能作为通用开放代理；
GET 请求幂等无敏感信息，函数 URL 可使用“免鉴权”方式。
"""
import re
import urllib.request
import urllib.error

UPSTREAM = "https://rss.cnki.net"
PATH_RE = re.compile(r"^/knavi/rss/[A-Za-z0-9]{2,8}/?$")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _resp(code, body, ctype="application/rss+xml; charset=utf-8"):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": ctype,
            "Cache-Control": "public, max-age=1800",
            "Access-Control-Allow-Origin": "*",
        },
        "body": body,
        "isBase64Encoded": False,
    }


def main_handler(event, context):
    ev = event if isinstance(event, dict) else {}
    path = ev.get("rawPath") or ev.get("path") or ""
    if not path:
        http = ((ev.get("requestContext") or {}).get("http") or {})
        path = http.get("path", "")

    if not PATH_RE.match(path):
        return _resp(404, "not found", "text/plain; charset=utf-8")

    url = UPSTREAM + path.rstrip("/")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "ignore")
        return _resp(200, body)
    except urllib.error.HTTPError as e:
        return _resp(e.code, "upstream http %s" % e.code, "text/plain; charset=utf-8")
    except Exception as e:
        return _resp(502, "upstream error: %s" % e, "text/plain; charset=utf-8")
