"""An empty completion must name the call and the provider's reason, not TypeError."""

from types import SimpleNamespace as NS

import pytest

from src.llm import EmptyCompletion, completion_text


def _resp(content="hi", finish="stop"):
    return NS(choices=[NS(message=NS(content=content, refusal=None), finish_reason=finish)])


def test_returns_the_content():
    assert completion_text(_resp()) == "hi"


def test_empty_string_is_content_not_an_error():
    assert completion_text(_resp("")) == ""


def test_no_choices_names_the_provider_error():
    # The shape OpenRouter produces for an upstream failure: HTTP 200, no
    # choices, an `error` object the SDK keeps as an extra field.
    resp = NS(choices=None, model_extra={"error": {"message": "upstream 503", "code": 503}})
    with pytest.raises(EmptyCompletion, match=r"normaliser: .*upstream 503"):
        completion_text(resp, label="normaliser")


def test_empty_choices_list_is_the_same_failure():
    with pytest.raises(EmptyCompletion, match="no choices"):
        completion_text(NS(choices=[], model_extra=None))


def test_none_content_reports_finish_reason():
    with pytest.raises(EmptyCompletion, match="finish_reason='content_filter'"):
        completion_text(_resp(None, "content_filter"))
