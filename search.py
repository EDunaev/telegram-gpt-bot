import requests, logging
from urllib.parse import urlparse
from datetime import datetime
from .config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX, client, current_model

_BAD_DOMAINS = {
    "google.com", "support.google.com", "policies.google.com",
    "accounts.google.com", "blog.google", "chrome.google.com"
}

def _is_bad_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return any(host.endswith(d) for d in _BAD_DOMAINS)
    except Exception:
        return False

def _one_call(query: str, num: int, lr: str | None, date_restrict: str | None):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": query,
        "num": max(1, min(num, 10)),
        "safe": "active",
        "hl": "ru",
    }
    if lr:
        params["lr"] = lr
    if date_restrict:
        params["dateRestrict"] = date_restrict

    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            logging.error("CSE HTTP %s: %s", r.status_code, r.text[:500])
            return []
        data = r.json()
    except Exception as e:
        logging.exception("CSE request error: %s", e)
        return []

    items = []
    for it in data.get("items", []) or []:
        link = it.get("link", "")
        if not link or _is_bad_domain(link):
            continue
        items.append({
            "title": it.get("title", "Без названия"),
            "link": link,
            "snippet": it.get("snippet", "")
        })
    logging.info("CSE ok (lr=%s, date=%s): %d results", lr, date_restrict, len(items))
    return items

def google_search(query: str, num_results: int = 8, date_restrict: str | None = "m6"):
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        raise RuntimeError("Google CSE ключи не заданы")

    res = _one_call(query, num_results, lr="lang_ru", date_restrict=date_restrict)
    if res:
        return res
    res = _one_call(query, num_results, lr=None, date_restrict=date_restrict)
    if res:
        return res
    return _one_call(query, num_results, lr=None, date_restrict=None)

def summarize_search_results(user_query: str, results: list) -> str:
    if not results:
        return "Ничего не нашёл по запросу."

    blocks = []
    for i, it in enumerate(results, 1):
        blocks.append(f"{i}. {it['title']}\n{it['snippet']}\n{it['link']}")
    corpus = "\n\n".join(blocks)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    system_prompt = (
        "Ты ассистент-аналитик результатов веб-поиска..."
        f"Текущая дата: {today}."
    )

    user_prompt = (
        f"Вопрос: «{user_query}».\n\n"
        f"{corpus}"
    )

    resp = client.chat.completions.create(
        model=current_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content
