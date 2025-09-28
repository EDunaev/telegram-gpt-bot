import logging
from datetime import datetime
from config import client, current_model

def summarize_search_results(user_query: str, results: list) -> str:
    if not results:
        return "Ничего не нашёл по запросу."

    logging.info("CSE raw: %s", results)
    blocks = []
    for i, it in enumerate(results, 1):
        blocks.append(f"{i}. {it['title']}\n{it['snippet']}\n{it['link']}")
    corpus = "\n\n".join(blocks)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    system_prompt = (
        "Ты ассистент-аналитик результатов веб-поиска. У тебя НЕТ прямого доступа в интернет; "
        "используй ТОЛЬКО предоставленные сниппеты и ссылки. "
        f"Текущая дата: {today}. "
        "Предпочитай свежие и надёжные источники. "
        "Не придумывай фактов. Если данных мало — лучше задай уточняющий вопрос."
    )

    user_prompt = (
        f"Вопрос пользователя: «{user_query}».\n\n"
        "Ниже результаты поиска. Выбери главное и представь краткий ответ. "
        "В конце добавь раздел «Источники» с 2–4 ссылками.\n\n"
        f"{corpus}"
    )

    resp = client.chat.completions.create(
        model=current_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content
