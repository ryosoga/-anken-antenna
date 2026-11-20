import hashlib
import warnings
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse

from categories import ALL_CATEGORY_KEYWORDS

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# リンクテキスト・URLに含まれていれば候補として拾うキーワード（一次フィルタ）
PICKUP_KEYWORDS = [
    # プロポーザル・委託系（必須）
    "プロポーザル", "企画提案", "企画競争", "公募型", "提案公募", "提案競技",
    "公募", "委託", "業務委託", "調達", "入札",
    # 全カテゴリのキーワードをマージ
    *ALL_CATEGORY_KEYWORDS,
]

# ナビゲーションなどの除外テキスト（完全一致）
SKIP_TEXTS = {
    "ホーム", "トップ", "サイトマップ", "お問い合わせ", "アクセス",
    "印刷", "文字サイズ", "ページの先頭へ", "English", "中文",
    "トップページ", "一覧を見る", "もっと見る", "詳細はこちら",
}


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _is_relevant_link(text: str, url: str) -> bool:
    if not text or len(text) < 6 or len(text) > 200:
        return False
    if text in SKIP_TEXTS:
        return False
    combined = text + url
    return any(kw in combined for kw in PICKUP_KEYWORDS)


def scrape_site(site: dict) -> list[dict]:
    items = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(site["url"], headers=headers, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
    except Exception as e:
        print(f"  ⚠️  取得失敗: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    base_host = urlparse(site["base_url"]).netloc

    seen_urls: set[str] = set()
    for a_tag in soup.find_all("a", href=True):
        text = a_tag.get_text(separator=" ", strip=True)
        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        full_url = urljoin(site["url"], href)
        link_host = urlparse(full_url).netloc

        # 同一ドメインのリンクのみ対象
        if link_host != base_host:
            continue
        if full_url in seen_urls:
            continue
        if full_url.lower().endswith('.pdf'):
            continue
        seen_urls.add(full_url)

        if _is_relevant_link(text, full_url):
            items.append({
                "id": _make_id(full_url),
                "title": text,
                "url": full_url,
                "site_name": site["name"],
                "prefecture": site["prefecture"],
                "category": site["category"],
            })

    return items


def scrape_all_sites(sites: list[dict]) -> list[dict]:
    all_items: list[dict] = []
    seen_ids: set[str] = set()

    for site in sites:
        print(f"  🔍 {site['name']}")
        items = scrape_site(site)
        # グローバル重複除去
        unique = [i for i in items if i["id"] not in seen_ids]
        for i in unique:
            seen_ids.add(i["id"])
        print(f"     → {len(unique)} 件")
        all_items.extend(unique)

    return all_items
