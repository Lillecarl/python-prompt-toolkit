from __future__ import annotations

import asyncio
from asyncio import run

from prompt_toolkit.eventloop.utils import call_soon_threadsafe


def test_call_soon_threadsafe_without_postponing():
    """
    Without a `max_postpone_time`, the callback is scheduled right away.
    """

    async def check():
        ran = []
        call_soon_threadsafe(lambda: ran.append("done"))
        await asyncio.sleep(0.05)
        return ran

    assert run(check()) == ["done"]


def test_a_postponed_call_runs_as_soon_as_the_loop_is_idle():
    """
    `max_postpone_time` is a deadline and not a delay.

    The callback runs as soon as the event loop has nothing else ready,
    so a long deadline on an idle loop still runs it at once.
    """

    async def check():
        ran = []
        call_soon_threadsafe(lambda: ran.append("done"), max_postpone_time=30.0)
        await asyncio.sleep(0.05)
        return ran

    assert run(check()) == ["done"]


def test_a_postponed_call_waits_while_the_loop_is_busy():
    """
    The point of postponing: a callback gives way to work that is
    already scheduled.
    """

    async def check():
        order = []

        async def keeps_the_loop_busy():
            for _ in range(20):
                order.append("other")
                await asyncio.sleep(0)

        busy = asyncio.ensure_future(keeps_the_loop_busy())
        call_soon_threadsafe(lambda: order.append("postponed"), max_postpone_time=30.0)
        await busy
        await asyncio.sleep(0.05)
        return order

    order = run(check())

    assert order.count("postponed") == 1
    assert order.index("postponed") > 0, "it did not give way to the other work"
