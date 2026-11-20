"""
案件アンテナ スクレイパー
GitHub Actions から毎日実行し、data/proposals.json を更新する
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from scraper import scrape_all_sites
from sites import SITES
from categories import CATEGORIES

JST = timezone(timedelta(hours=9))


def classify_category(title: str) -> str:
    """タイトルのキーワードからカテゴリを判定する"""
    for cat_name, keywords in CATEGORIES.items():
        if any(kw in title for kw in keywords):
            return cat_name
    return "その他・委託全般"


def normalize_prefecture(raw: str) -> str:
    """'島根県（松江市）' → '島根県' に正規化"""
    for pref in ["島根県", "鳥取県", "広島県", "岡山県", "山口県"]:
        if pref in raw:
            return pref
    return raw


def run():
    print(f"[{datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST] スクレイピング開始")

    raw_items = scrape_all_sites(SITES)

    proposals = []
    seen_urls = set()

    for item in raw_items:
        url = item["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        prefecture = normalize_prefecture(item.get("prefecture", ""))
        category   = classify_category(item["title"])

        # org名: site_nameから県名部分を除いたもの
        org = item.get("site_name", "")

        proposals.append({
            "title":      item["title"],
            "url":        url,
            "prefecture": prefecture,
            "org":        org,
            "category":   category,
        })

    output = {
        "updated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "total":      len(proposals),
        "proposals":  proposals,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "proposals.json")
    out_path = os.path.normpath(out_path)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"完了: {len(proposals)} 件 → {out_path}")


if __name__ == "__main__":
    run()
