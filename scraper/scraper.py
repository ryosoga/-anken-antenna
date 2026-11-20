import hashlib
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
# タイトルまたはURLにいずれか1つ含まれていなければ除外
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
    "【審査結果】",
    "事業者の決定について", "事業者を選定", "事業者が決定",
    "候補者を選定しました",
    "審査結果を公表", "審査結果公表中", "審査結果を掲載",
    r"（審査結果公表）",
    "選定結果", "採択結果", "採択者の決定",
    r"（選考結果）",
    "の結果について$",
    "結果を公表しました", "終了しました", "プロポーザルは終了",
    "落札者", "契約締結",
]


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _is_relevant_link(text: str, url: str) -> bool:
    import re
    if not text or len(text) < 8 or len(text) > 200:
        return False
    if text in SKIP_TEXTS:
        return False
    # 除外パターンにマッチしたら捨てる
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, text):
            return False
    combined = text + url
    # 一次フィルタ：委託・入札系キーワードが含まれること
    if not any(kw in combined for kw in PICKUP_KEYWORDS):
        return False
    # 二次フィルタ：プロポーザル・企画提案であることが明示されていること
    # → 灯油調達・設備工事・物品賃貸借など、委託以外の調達を弾く
    return any(kw in combined for kw in PROPOSAL_CONFIRM_KEYWORDS)


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
