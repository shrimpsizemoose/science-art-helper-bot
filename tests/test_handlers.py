from src.handlers import is_valid_event_code, suggest_event_code


def test_suggest_event_code_simple():
    assert suggest_event_code("Hello World") == "hello_world"


def test_suggest_event_code_special_chars():
    assert suggest_event_code("Python Workshop!!! 2025") == "python_workshop_2025"


def test_suggest_event_code_cyrillic_generates_hash():
    # Cyrillic-only title should generate a hash fallback
    result = suggest_event_code("Воркшоп")
    assert len(result) == 12  # md5 hex[:12]
    assert is_valid_event_code(result)


def test_suggest_event_code_mixed_keeps_ascii():
    # Mixed title keeps ASCII parts
    assert suggest_event_code("Воркшоп Python 2025") == "python_2025"


def test_suggest_event_code_long():
    long_title = (
        "This is a very long title that should be truncated to fifty characters"
    )
    result = suggest_event_code(long_title)
    assert len(result) <= 50


def test_suggest_event_code_multiple_spaces():
    assert suggest_event_code("Hello    World") == "hello_world"


def test_suggest_event_code_leading_trailing():
    assert suggest_event_code("  Hello World  ") == "hello_world"


def test_is_valid_event_code_valid():
    assert is_valid_event_code("hello_world") is True
    assert is_valid_event_code("event2025") is True
    assert is_valid_event_code("my_event_123") is True


def test_is_valid_event_code_invalid():
    assert is_valid_event_code("Hello World") is False  # spaces
    assert is_valid_event_code("event-2025") is False  # hyphen
    assert is_valid_event_code("Воркшоп") is False  # cyrillic
    assert is_valid_event_code("EVENT") is False  # uppercase
    assert is_valid_event_code("") is False  # empty


def test_is_valid_event_code_length():
    # 64 chars is max
    assert is_valid_event_code("a" * 64) is True
    assert is_valid_event_code("a" * 65) is False
