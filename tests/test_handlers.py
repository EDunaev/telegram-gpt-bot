import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock


from gpt_bot import (
    start,
    help_cmd,
    set_model,
    handle_text,
    is_allowed,
    ADMINS,
    CHAT_ID,
    BOT_USERNAME,
    current_model,
)

class DummyUser:
    def __init__(self, user_id, username='testuser'):
        self.id = user_id
        self.username = username

class DummyChat:
    def __init__(self, chat_id, chat_type='private'):
        self.id = chat_id
        self.type = chat_type

class DummyMessage:
    def __init__(self, text="", caption=None):
        self.text = text
        self.caption = caption
        self.replies = []

    async def reply_text(self, msg):
        self.replies.append(msg)

class DummyUpdate:
    def __init__(self, user_id, chat_id, text="", chat_type="private", caption=None):
        self.effective_user = DummyUser(user_id)
        self.effective_chat = DummyChat(chat_id, chat_type)
        self.message = DummyMessage(text=text, caption=caption)

@pytest.mark.asyncio
async def test_start_admin():
    update = DummyUpdate(user_id=list(ADMINS)[0], chat_id=CHAT_ID)
    context = MagicMock()
    await start(update, context)
    assert any("сменить модель" in r for r in update.message.replies)


def test_is_allowed_admin():
    update = DummyUpdate(user_id=list(ADMINS)[0], chat_id=CHAT_ID)
    assert is_allowed(update)

def test_is_allowed_group_with_mention():
    update = DummyUpdate(user_id=999999, chat_id=CHAT_ID, chat_type="group", text=f"@{BOT_USERNAME}")
    assert is_allowed(update)

def test_is_allowed_group_without_mention():
    update = DummyUpdate(user_id=999999, chat_id=CHAT_ID, chat_type="group", text="Привет")
    assert not is_allowed(update)

@pytest.mark.asyncio
async def test_help_command_admin():
    update = DummyUpdate(user_id=list(ADMINS)[0], chat_id=CHAT_ID)
    context = MagicMock()
    await help_cmd(update, context)
    assert any("/quota" in r for r in update.message.replies)

@pytest.mark.asyncio
async def test_set_model_as_admin():
    update = DummyUpdate(user_id=list(ADMINS)[0], chat_id=CHAT_ID, text="/model gpt-3.5-turbo")
    context = MagicMock()
    context.args = ["gpt-3.5-turbo"]
    await set_model(update, context)
    assert "gpt-3.5-turbo" in update.message.replies[0]


