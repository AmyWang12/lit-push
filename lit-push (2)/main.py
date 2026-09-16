"""lit-push 入口：采集 → 过滤 → 去重 → (可选 LLM) → 排序 → 归档/推送。

本地运行:
    pip install -r requirements.txt
    python main.py --config config.yaml
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timedelta, timezone

from litpush import classify, delivery, processing, sources
from litpush.utils import load_config, setup_logging


def run(config_path: str) -> int:
    cfg = load_config(config_path)
    log = setup_logging()

    tz_name = (cfg.get("runtime", {}) or {}).get("timezone", "Asia/Shanghai")
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now(timezone(timedelta(hours=8)))
    today = now.strftime("%Y-%m-%d")
    log.info("===== 文献推送任务开始 %s =====", today)

    try:
        papers = sources.collect_all(cfg, log)
        papers = processing.filter_papers(papers, cfg, log)
        papers, seen = processing.dedup_new(papers, cfg, log)
        papers = processing.enrich_with_llm(papers, cfg, log)
        classify.apply_rule_classification(papers, cfg)   # LLM 未归类的由规则兜底
        papers = processing.rank_papers(papers, cfg)

        success_channels = delivery.deliver(papers, today, cfg, log)
        if success_channels > 0:
            processing.save_seen(seen, papers, cfg)
            log.info("去重记录已保存，本次推送 %d 篇", len(papers))
        else:
            log.error("推送全部失败，保留去重记录不变，下次自动重试")
            return 2

        log.info("===== 任务完成 =====")
        return 0
    except Exception:
        log.error("任务异常:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="个人专属文献推送系统")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    sys.exit(run(parser.parse_args().config))
