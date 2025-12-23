from src.handlers import slugify


def test_slugify_simple():
    assert slugify("Hello World") == "hello_world"


def test_slugify_special_chars():
    assert slugify("Python Workshop!!! 2025") == "python_workshop_2025"


def test_slugify_keeps_cyrillic():
    assert slugify("Воркшоп Python") == "воркшоп_python"


def test_slugify_long():
    long_title = (
        "This is a very long title that should be truncated to fifty characters"
    )
    result = slugify(long_title)
    assert len(result) <= 50


def test_slugify_multiple_spaces():
    assert slugify("Hello    World") == "hello_world"


def test_slugify_leading_trailing():
    assert slugify("  Hello World  ") == "hello_world"
