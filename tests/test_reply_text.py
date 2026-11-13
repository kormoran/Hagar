"""Test della normalizzazione content/reasoning."""

from __future__ import annotations

from llm.reply_text import clean_text, reply_text


def test_normal_content_is_unchanged():
    assert clean_text("Risposta normale") == "Risposta normale"


def test_lmstudio_reasoning_fallback():
    text, fallback = reply_text("", "OK")

    assert text == "OK"
    assert fallback is True


def test_empty_content_without_reasoning():
    text, fallback = reply_text("", "")

    assert text == ""
    assert fallback is False


def test_special_tokens_and_turn_tags():
    assert clean_text(
        "<|im_start|>assistant\nOK<|im_end|>"
    ) == "OK"
    assert clean_text(
        "<start_of_turn>model\nOK<end_of_turn>"
    ) == "OK"


def test_answer_and_thought_tags():
    assert clean_text(
        "<thinking>analisi interna</thinking>"
        "<answer>OK</answer>"
    ) == "OK"
    assert clean_text("<|channel|>thought\nracconto\n"
                      "<|channel|>final\nOK") == "racconto\nOK"


def test_generic_single_wrapper_is_unwrapped():
    assert clean_text("<custom>OK</custom>") == "OK"


def test_html_is_not_unwrapped():
    assert clean_text("<b>ciao</b>") == "<b>ciao</b>"


def test_reasoning_is_cleaned_too():
    text, fallback = reply_text(
        "",
        "<thinking>x</thinking>OK",
    )

    assert text == "OK"
    assert fallback is True
