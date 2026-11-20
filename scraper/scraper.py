import hashlib
import re
import warnings
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# 一次フィルタ：いずれか含めばリンクを候補として拾う
PICKUP_KEYWORDS = [
    "プロポーザル", "企画提案", "企画競争", "公募型", "提案公募", "提案競技",
    "委託", "業務委託", "調達公告", "入札公告", "指名競争",
]

# 二次フィルタ：プロポーザル・企画提案であることを確認するキーワード（必須）
PROPOSAL_CONFIRM_KEYWORDS = [
    "プロポーザル", "企画提案", "企画競争", "提案競技", "提案公募", "公募型",
]

# ナビゲーション・汎用リンクの除外テキスト（完全一致）
SKIP_TEXTS = {
    "ホーム", "トップ", "サイトマップ", "お問い合わせ", "アクセス",
    "印刷", "文字サイズ", "ページの先頭へ", "English", "中文",
    "トップページ", "一覧を見る", "もっと見る", "詳細はこちら",
}

# タイトルにこれらが含まれていたら除外（ノイズ・募集終了案件）
EXCLUDE_PATTERNS = [
    # 広報誌・案内系のノイズ
    "広報誌", "広報紙", "広報.*号に掲載", "情報誌", "市報", "町報",
    "年男", "年女", "生まれ", "募集します！",
    "パブリックコメント", "意見募集",
    "採用試験", "職員募集", "会計年度任用",
    "ふるさと納税", "ふるさと寄附",
    "広告掲載",
    # 制度案内・参加資格・規則類
    "入札参加資格.*名簿", "入札参加資格.*変更", "入札参加資格.*申請",
    "入札参加資格に関する", "入札参加資格$",
    "参加資格の変更申請", "参加資格に関する変更",
    "取扱要領", "契約約款", "労務単価", "技術者単価", "特例措置",
    "入札.*結果.*公表", "契約.*結果.*公表",
    "内訳書の記載", "閲覧用設計書",
    "電子入札.*有効", "指名競争入札.*有効",
    "優良業者優先指名", "資格要件を定め",
    "スライド条項",
    # 建設・土木工事（プロポーザルではなく請負工事）
    "建設工事.*入札", "入札公告.*工事", "工事.*入札公告",
    "下水道.*入札公告", "山腹工事", "護岸工事", "舗装工事", "橋梁工事",
    # 指名競争入札（プロポーザルではない）
    "指名競争入札の参加者を募集", "簡易公募型指名競争入札", "公募型指名競争入札",
    # 募集終了・結果公表済み
    "【審査結果】", "【募集終了】",
    "事業者の決定について", "事業者を選定", "事業者が決定",
    "候補者を選定しました",
    "審査結果を公表", "審査結果公表中", "審査結果を掲載",
    r"[（(]審査結果公表[）)]", r"[（(]審査結果[）)]",
    "選定結果", "採択結果", "採択者の決定",
    r"（選考結果）",
    "の結果について$",
    "審査結果について$", "プロポーザル審査結果について$",
    r"（終了）$",
    "を実施しました$", "プロポーザルを実施しました$",
    "結果を公表しました", "終了しました", "プロポーザルは終了",
    "落札者", "契約締結",
]

# このパターンに一致するタイトルは「一覧ページ」と判定し、
# そのURLをもう1段階スクレイプして個別案件を取得する
INDEX_PAGE_PATTERNS = [
    r"^プロポーザル（提案競技）$",
    r"^公募型プロポーザル$",
    r"^プロポーザル方式による発注のお知らせ$",
    r"^プロポーザル情報$",
    r"^プロポーザル$",
    r".{1,30}におけるプロポーザルの実施$",
    r"プロポーザル.{0,10}一覧",
    r"^業務委託.{0,15}（入札・契約）",
    r"入札・契約情報$",
    r"調達情報$",
    r"企画競争情報$",
    r"企画競争情報（.{1,20}）$",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _is_relevant_link(text: str, url: str) -> bool:
    if not text or len(text) < 8 or len(text) > 200:
        return False
    if text in SKIP_TEXTS:
        return False
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, text):
            return False
    combined = text + url
    if not any(kw in combined for kw in PICKUP_KEYWORDS):
        return False
    return any(kw in combined for kw in PROPOSAL_CONFIRM_KEYWORDS)


def _is_index_page(title: str) -> bool:
    """取得したリンクが一覧ページかどうかを判定する"""
    return any(re.search(pat, title) for pat in INDEX_PAGE_PATTERNS)


def _fetch_links(url: str, base_host: str) -> list[tuple[str, str]]:
    """urlを取得してリンク一覧（text, full_url）を返す。失敗時は空リスト"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
    except Exception as e:
        print(f"    ⚠️  取得失敗: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(separator=" ", strip=True)
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        full_url = urljoin(url, href)
        if urlparse(full_url).netloc != base_host:
            continue
        if full_url in seen or full_url.lower().endswith(".pdf"):
            continue
        seen.add(full_url)
        links.append((text, full_url))
    return links


def scrape_site(site: dict, seen_ids: set, depth: int = 0) -> list[dict]:
    """
    siteをスクレイプして案件リストを返す。
    depth=0 のとき、一覧ページと判定したリンクは再帰的にスクレイプする（depth=1まで）。
    """
    base_host = urlparse(site["base_url"]).netloc
    links = _fetch_links(site["url"], base_host)
    items = []

    for text, full_url in links:
        uid = _make_id(full_url)
        if uid in seen_ids:
            continue

        if _is_relevant_link(text, full_url):
            seen_ids.add(uid)
            items.append({
                "id":         uid,
                "title":      text,
                "url":        full_url,
                "site_name":  site["name"],
                "prefecture": site["prefecture"],
                "category":   site["category"],
            })

            # 一覧ページと判定したら1段階潜る
            if depth == 0 and _is_index_page(text):
                sub_site = {**site, "url": full_url}
                sub_items = scrape_site(sub_site, seen_ids, depth=1)
                if sub_items:
                    print(f"      ↳ 一覧ページ深掘り: {len(sub_items)} 件追加")
                items.extend(sub_items)

    return items


def scrape_all_sites(sites: list[dict]) -> list[dict]:
    all_items: list[dict] = []
    seen_ids: set[str] = set()

    for site in sites:
        print(f"  🔍 {site['name']}")
        items = scrape_site(site, seen_ids, depth=0)
        print(f"     → {len(items)} 件")
        all_items.extend(items)

    return all_items
