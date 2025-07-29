from types import SimpleNamespace
from gpt_bot import is_allowed, ADMINS, CHAT_ID

def make_fake_update(user_id, chat_type, chat_id, text=None, caption=None):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        message=SimpleNamespace(text=text, caption=caption)
    )

def test_admin_private_allowed():
    update = make_fake_update(user_id=list(ADMINS)[0], chat_type="private", chat_id=123)
    assert is_allowed(update)

def test_group_mention_required():
    update = make_fake_update(user_id=999999, chat_type="supergroup", chat_id=CHAT_ID, text="Привет @DunaevAssistentBot")
    assert is_allowed(update)

def test_group_without_mention_denied():
    update = make_fake_update(user_id=999999, chat_type="supergroup", chat_id=CHAT_ID, text="Привет")
    assert not is_allowed(update)

def test_other_group_denied():
    update = make_fake_update(user_id=999999, chat_type="supergroup", chat_id=11111, text="Привет @DunaevAssistentBot")
    assert not is_allowed(update)
