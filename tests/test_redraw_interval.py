from __future__ import annotations

import asyncio

from prompt_toolkit.application import Application
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput


def test_a_redraw_interval_unset_while_a_redraw_waits():
    """
    A redraw that has to wait for `min_redraw_interval` still runs
    when the interval is unset before the wait begins.
    """
    reported = []

    async def main() -> None:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda loop, context: reported.append(context))

        with create_pipe_input() as pipe:
            app = Application(input=pipe, output=DummyOutput(), min_redraw_interval=0.2)

            async def drive() -> None:
                await asyncio.sleep(0.05)
                app.invalidate()
                await asyncio.sleep(0)
                app.invalidate()
                # The second has to wait, and the interval goes first.
                app.min_redraw_interval = None
                await asyncio.sleep(0.4)
                app.exit()

            driving = asyncio.ensure_future(drive())
            await app.run_async(set_exception_handler=False)
            await driving

    asyncio.run(main())

    assert reported == []
