"""
案件アンテナ スクレイパー
GitHub Actions から毎日実行し、data/proposals.json を更新する
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from scraper import scrape_all_sites
from sites import SITES
from categories import CATEGORIES

JST = timezone(timedelta(hours=9))

# タイトルから除去する「更新情報」の接頭辞・接尾辞パターン
# 除去後に残ったテキストが元案件タイトル、is_updated=Trueを付ける
UPDATE_PATTERNS = [
    r"【更新】",
    r"【掲載】",
    r"＞＞",
    r"《[^》]*》",                        # 《審査結果公表中》など
    r"〔[^〕]*〕",
    r"質問に対する回答を(掲載|追加)しました",
    r"質問への回答を掲載しました",
    r"回答を掲載しました",
    r"質問回答を掲載しました",
    r"掲載しました$",
    r"を更新しました$",
    r"について掲載しました$",
    r"について更新しました$",
]


def classify_category(title: str) -> str:
    for cat_name, keywords in CATEGORIES.items():
        if any(kw in title for kw in keywords):
            return cat_name
    return "その他・委託全般"


def normalize_prefecture(raw: str) -> str:
    for pref in ["島根県", "鳥取県", "広島県", "岡山県", "山口県"]:
        if pref in raw:
            return pref
    return raw


def clean_title(raw: str) -> tuple[str, bool]:
    """更新系テキストを除去してクリーニング済みタイトルと更新フラグを返す"""
    cleaned = raw
    is_updated = False
    for pat in UPDATE_PATTERNS:
        new = re.sub(pat, "", cleaned).strip()
        if new != cleaned:
            is_updated = True
            cleaned = new
    # 先頭に孤立した「】」が残った場合（【XXX】の【だけ除去されたケース）を除去
    cleaned = re.sub(r"^[^【】]*】\s*", "", cleaned) if re.match(r"^[^【】]+】", cleaned) else cleaned
    # 先頭の空白・記号を除去
    cleaned = re.sub(r"^[　\s・＞>]+", "", cleaned).strip()
    return cleaned, is_updated


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
        clean, is_updated = clean_title(item["title"])
        category = classify_category(clean)
        org = item.get("site_name", "")

        proposals.append({
            "title":      clean,
            "url":        url,
            "prefecture": prefecture,
            "org":        org,
            "category":   category,
            "is_updated": is_updated,
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
