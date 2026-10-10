"""
The buffer filters answer without building a dummy buffer.

With no buffer focused, `Application.current_buffer` builds a whole
`Buffer` to stand in for one. The filters answer what that dummy would
from the layout instead, and never ask for it.
"""

from __future__ import annotations

import pytest

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import (
    completion_is_selected,
    has_completions,
    has_focus,
    has_selection,
    has_suggestion,
    has_validation_error,
    is_multiline,
    is_read_only,
)
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import DummyOutput

FILTERS = [
    has_selection,
    has_suggestion,
    has_completions,
    completion_is_selected,
    is_read_only,
    is_multiline,
    has_validation_error,
    has_focus("dummy-buffer"),
    has_focus("another"),
    has_focus(Buffer()),
]


@pytest.fixture
def no_buffer_focused():
    window = Window(FormattedTextControl("text"))
    app = Application(layout=Layout(window), input=DummyInput(), output=DummyOutput())
    with set_app(app):
        yield app


def test_each_filter_answers_what_a_dummy_buffer_would(no_buffer_focused):
    dummy = no_buffer_focused.current_buffer
    expected = [
        bool(dummy.selection_state),
        dummy.suggestion is not None,
        dummy.complete_state is not None,
        dummy.complete_state is not None,
        dummy.read_only(),
        dummy.multiline(),
        dummy.validation_error is not None,
        True,
        False,
        False,
    ]
    assert [bool(f()) for f in FILTERS] == expected


def test_no_filter_builds_a_dummy_buffer(no_buffer_focused, monkeypatch):
    def refuse(self):
        raise AssertionError("a filter asked for current_buffer")

    monkeypatch.setattr(Application, "current_buffer", property(refuse))
    for f in FILTERS:
        f()
