import logging
from config import client, current_model

def should_web_search(user_input: str) -> bool:
    """
    Решает, нужен ли веб-поиск. Использует GPT для интерпретации запроса.
    """
    decision_prompt = (
        "Определи, нужен ли интернет-поиск. Ответь ровно 'YES' или 'NO'.\n"
        f"Запрос: {user_input}"
    )
    try:
        decision = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": decision_prompt}],
            max_tokens=3
        ).choices[0].message.content.strip().upper()

        if decision == "YES":
            logging.info("Запрос в интернете")
            return True
        else:
            logging.info("Запрос обработается без интернета")
            return False
    except Exception as e:
        logging.error("Ошибка в should_web_search: %s", e)
        return False
