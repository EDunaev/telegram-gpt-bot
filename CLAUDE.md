# telegram-gpt-bot

Telegram-бот на `python-telegram-bot` + OpenAI API. Личный ассистент автора: приватный чат с GPT
для админов и ограниченный доступ в одной групповой беседе.

## Архитектура

Весь бот — один файл: [gpt_bot.py](gpt_bot.py). Это единственный модуль, который реально
запускается (`python gpt_bot.py`) и который импортируют тесты. В нём в одном месте лежат:
конфиг/инициализация env, access control, хендлеры команд и сообщений, веб-поиск (Google CSE) и
суммаризация результатов через ту же модель.

`logger.py` — отдельный модуль с настройкой `RotatingFileHandler` (`bot.log`, 5×5MB), реально
используется (`from logger import setup_logger`).

Раньше в репозитории лежала параллельная модульная версия (`config.py`, `handlers.py`,
`search.py`, `utils.py`) — незавершённый рефакторинг на пакетную структуру с относительными
импортами (`from .config import ...`), но без `__init__.py` в корне. Она нигде не импортировалась
и была нерабочей (сломанные relative imports). Удалена — **не переносить сюда логику из старых
коммитов, gpt_bot.py — источник истины**.

## Запуск

```
pip install python-telegram-bot openai python-dotenv requests pydub
python gpt_bot.py
```

Нет `requirements.txt` — зависимости ставятся вручную. Нужен `.env` в корне с минимум:
`TELEGRAM_TOKEN`, `OPENAI_API_KEY`. Опционально: `OPENAI_MODEL` (default `gpt-3.5-turbo`),
`DECISION_MODEL`, `VISION_MODEL` (default `gpt-4o-mini`), `GOOGLE_CSE_API_KEY`/`GOOGLE_API_KEY`,
`GOOGLE_CSE_CX`/`GOOGLE_CSE_ID`.

## Тесты

```
python -m pytest -q
```

`handle_voice` делает `from pydub import AudioSegment` **лениво, внутри функции**, а не на
верхнем уровне модуля — специально, чтобы импорт `gpt_bot.py` не падал на окружениях без
`audioop` (убрали в новых версиях Python) и текстовые тесты не зависели от pydub/ffmpeg.
Не поднимать этот импорт обратно наверх файла.

## Access control (`is_allowed`)

- Приватный чат + `user_id in ADMINS` → всегда разрешено.
- Групповой чат с `chat.id == CHAT_ID` и типом `group`/`supergroup` → разрешено только если в
  тексте есть упоминание `BOT_USERNAME`, либо сообщение — reply на сообщение бота.
- Всё остальное — запрещено.

Каждый хендлер, который что-то делает (`search_cmd`, `reset`, и т.д.), обязан сам вызвать
`is_allowed(update)` в начале и выйти, если `False` — это не middleware, а ручная проверка в
каждой функции. При добавлении нового хендлера не забыть эту проверку (в прошлом `search_cmd` и
`reset` были без неё — дыра в правах, уже пофикшена).

`ADMINS`, `LIMITED_USERS`, `CHAT_ID`, `BOT_USERNAME` — захардкожены константами в
[gpt_bot.py](gpt_bot.py), не в `.env`.

## Веб-поиск

`google_search()` — Google Custom Search API с fallback-цепочкой по убыванию строгости:
без ограничения языка + `dateRestrict` → без языка и без `dateRestrict`. Результаты фильтруются
через `_is_bad_domain` (отсекает служебные google.com-домены). `summarize_search_results()`
суммаризирует найденное текущей моделью (`current_model`), без прямого доступа модели в интернет.

Режим переключается кнопками (`🌐 Веб-поиск` / `💬 Обычный чат`) только в приватных чатах, либо
явной командой `/web <текст>` и `/search <текст>`.

## Распознавание картинок (`handle_photo`)

Фото (`filters.PHOTO`) и изображения, присланные как файл (`Document.IMAGE`), обрабатываются
`handle_photo` — остальные документы и видео по-прежнему уходят в `handle_unsupported`
(`Document.ALL & ~Document.IMAGE | filters.VIDEO`). Картинка скачивается через `get_file()` →
`download_as_bytearray()`, кодируется в base64 и отправляется в `chat.completions.create` как
`image_url` с data-URL (`data:image/jpeg;base64,...`), caption пользователя — как текст вопроса
(дефолт: "Что на этой картинке?").

Используется **отдельная константа `VISION_MODEL`** (env, default `gpt-4o-mini`), а не
`current_model` — потому что `current_model` меняется командой `/model` на произвольную модель,
и не каждая такая модель поддерживает vision. Если бы `handle_photo` брал `current_model`, фича
могла бы сломаться после `/model gpt-3.5-turbo`. Не заменять `VISION_MODEL` на `current_model`
в `handle_photo`.

Общая vision-логика вынесена в хелперы `_extract_image_source(msg)` (фото или картинка-документ
у сообщения → объект с `.get_file()`, иначе `None`), `_download_image_b64(image_source)` и
`_ask_vision(prompt_text, image_b64)`. Используются и в `handle_photo`, и в `handle_text`.

### Reply текстом на сообщение с картинкой (в группе — единственная память бота)

В групповых чатах у бота нет истории диалога вообще — единственный способ дать боту контекст
предыдущего сообщения — ответить (reply) на него. `handle_text` проверяет `message.reply_to_message`
через `_extract_image_source`: если реплай идёт на сообщение с картинкой (**от бота или от любого
другого пользователя** — не только от бота), запрос уходит в vision (`_ask_vision`) с текстом
реплая как вопросом, а не в обычный текстовый чат. Раньше этой проверки не было: `handle_text`
подхватывал контекст реплая, только если `reply_to_message.from_user.username == BOT_USERNAME` и
только `.text` (никогда `.photo`) — поэтому reply текстом на чужое фото-сообщение в группе (например
"объясни шутку на фото") молча уходил в обычный GPT-чат без картинки, и модель отвечала что-то вроде
"пришли фото", хотя фото уже было отправлено раньше в чат. Если снова трогать этот блок — не терять
проверку `_extract_image_source(replied)`, иначе баг вернётся.

## Известные проблемы / долги

- `quota()` дёргает `https://api.openai.com/dashboard/billing/credit_grants` — этот endpoint
  давно депрекейтнут OpenAI, скорее всего не работает и требует замены на актуальный billing API.
- Нет `requirements.txt` и `.env.example`.
- `LIMITED_USERS` объявлен, но нигде не используется в логике.
