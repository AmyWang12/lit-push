"""lit-push: 个人专属文献推送系统。

模块组成:
    sources     多源采集 (arXiv / PubMed / 通用 RSS)
    processing  关键词筛选、SQLite/JSON 去重、可选 LLM 摘要评分
    delivery    Markdown/HTML 渲染与多渠道推送 (邮件/Telegram/飞书/微信)
"""

__version__ = "1.0.0"
