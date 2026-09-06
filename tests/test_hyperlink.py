"""
Hyperlinks (OSC 8).

A link belongs to a cell, so it travels in the style string of that
cell and comes out of `Attrs`. The target is base64, because a style
string is split on whitespace and a URL can hold anything.

A link also carries an id. The id joins the pieces of one link, so a
link that a line break cuts in two is still one link. It travels the
same way the target does.
"""
import base64
from itertools import zip_longest

from prompt_toolkit.output.color_depth import ColorDepth
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.styles import Attrs, Style


def token(target: str) -> str:
    return "[hyperlink:%s]" % base64.b64encode(target.encode()).decode()


def id_token(link_id: str) -> str:
    return "[hyperlink-id:%s]" % base64.b64encode(link_id.encode()).decode()


def attrs_of(style_str: str) -> Attrs:
    return Style([]).get_attrs_for_style_str(style_str)


def test_a_style_string_carries_a_target():
    assert attrs_of(token("https://example.com")).hyperlink == "https://example.com"


def test_a_target_can_hold_a_space():
    assert attrs_of(token("https://example.com/a b")).hyperlink == (
        "https://example.com/a b"
    )


def test_a_target_can_hold_text_of_a_user():
    assert attrs_of(token("https://example.com/är")).hyperlink == (
        "https://example.com/är"
    )


def test_an_empty_token_takes_the_link_away():
    assert attrs_of("[hyperlink:]").hyperlink == ""


def test_a_target_that_is_not_base64_is_no_link():
    # A style string is split on whitespace, so a token never holds a
    # space. What can arrive is a token that does not decode.
    assert attrs_of("[hyperlink:####]").hyperlink == ""
    assert attrs_of("[hyperlink:aGVsbG8=extra]").hyperlink == ""


def test_a_target_with_a_control_character_is_no_link():
    "An escape would end the sequence early, and what follows would run."
    assert attrs_of(token("https://a\x1b]0;owned\x07")).hyperlink == ""
    assert attrs_of(token("https://a\x07b")).hyperlink == ""


def test_the_rest_of_the_style_still_works():
    attrs = attrs_of("bold bg:#ff0000 " + token("https://example.com"))
    assert attrs.bold is True
    assert attrs.bgcolor == "ff0000"
    assert attrs.hyperlink == "https://example.com"


class _Stdout:
    encoding = "utf-8"

    def __init__(self):
        self.data = []

    def write(self, text):
        self.data.append(text)

    def flush(self):
        pass

    def isatty(self):
        return True

    def fileno(self):
        raise OSError


def written(targets, ids=()):
    """
    Feed a list of targets to the output and return what it wrote.

    `ids` gives the id of each target, for a test that is about the id.
    A target with no id in the list goes out without one.
    """
    stdout = _Stdout()
    output = Vt100_Output(stdout, lambda: None, term="xterm")
    for target, link_id in zip_longest(targets, ids, fillvalue=""):
        output.set_attributes(
            Attrs(
                color="",
                bgcolor="",
                bold=False,
                underline=False,
                strike=False,
                italic=False,
                blink=False,
                reverse=False,
                hidden=False,
                dim=False,
                hyperlink=target,
                hyperlink_id=link_id,
            ),
            ColorDepth.DEPTH_8_BIT,
        )
    return "".join(output._buffer)


def test_a_link_opens_and_closes():
    data = written(["https://example.com", ""])
    assert "\x1b]8;;https://example.com\x1b\\" in data
    assert data.endswith("\x1b]8;;\x1b\\")


def test_a_link_goes_out_once():
    "Cell after cell of the same link needs no sequence of its own."
    data = written(["https://example.com", "https://example.com"])
    assert data.count("\x1b]8;;https://example.com\x1b\\") == 1


def test_a_second_link_replaces_the_first():
    data = written(["https://a", "https://b"])
    assert data.index("\x1b]8;;https://a\x1b\\") < data.index("\x1b]8;;https://b\x1b\\")


def test_a_style_string_carries_an_id():
    attrs = attrs_of(token("https://example.com") + " " + id_token("42"))
    assert attrs.hyperlink == "https://example.com"
    assert attrs.hyperlink_id == "42"


def test_an_id_goes_out_in_the_parameter_field():
    data = written(["https://example.com"], ["42"])
    assert "\x1b]8;id=42;https://example.com\x1b\\" in data


def test_a_new_id_opens_the_same_target_again():
    "Two ids are two links, whatever the target says."
    data = written(["https://a", "https://a"], ["1", "2"])
    assert data.count("\x1b]8;id=1;https://a\x1b\\") == 1
    assert data.count("\x1b]8;id=2;https://a\x1b\\") == 1


def test_one_id_goes_out_once():
    data = written(["https://a", "https://a"], ["1", "1"])
    assert data.count("\x1b]8;id=1;https://a\x1b\\") == 1


def test_a_link_that_closes_carries_no_id():
    "There is nothing left to join, so the id says nothing."
    data = written(["https://a", ""], ["1", "1"])
    assert data.endswith("\x1b]8;;\x1b\\")


def test_an_id_that_would_break_the_sequence_never_goes_out():
    """
    Three characters separate the parts of an "OSC 8", and a control
    character ends it early. An id that holds one is dropped, and the
    link still opens.
    """
    for bad in ("a;b", "a:b", "a=b", "a\x1bb", "a\x07b"):
        data = written(["https://a"], [bad])
        assert data.count("\x1b]8;;https://a\x1b\\") == 1


def test_an_id_stops_at_the_length_the_specification_gives():
    assert written(["https://a"], ["i" * 250]).count("id=") == 1
    assert written(["https://a"], ["i" * 251]).count("id=") == 0


def test_a_reset_closes_an_open_link():
    stdout = _Stdout()
    output = Vt100_Output(stdout, lambda: None, term="xterm")
    output.set_attributes(
        Attrs("", "", False, False, False, False, False, False, False, False,
              "https://example.com"),
        ColorDepth.DEPTH_8_BIT,
    )
    output.reset_attributes()
    assert "".join(output._buffer).endswith("\x1b[0m\x1b]8;;\x1b\\")
