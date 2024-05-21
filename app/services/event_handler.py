import asyncio
from typing import AsyncIterator, Literal, Union, cast

from openai import AsyncAssistantEventHandler
from openai.types.beta import AssistantStreamEvent
from typing_extensions import override
from openai.types.beta.threads import Text, TextDelta
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta
import os
import json
from deta import Deta
DETA_DATA_KEY = os.environ.get('DETA_DATA_KEY')
detalog = Deta(DETA_DATA_KEY).Base('assistant')


class EventHandler(AsyncAssistantEventHandler):
    """Async event handler that provides an async iterator."""

    queue: asyncio.Queue[str]
    done: asyncio.Event

    def __init__(self):
        super().__init__()
        self.queue = asyncio.Queue()
        self.done = asyncio.Event()

    @override
    async def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)
        self.done.clear()

    @override
    async def on_text_delta(self, delta, snapshot) -> None:
        print(delta.value, end="", flush=True)
        if delta.value is not None and delta.value != "":
            self.queue.put_nowait(delta.value)

    @override
    async def on_end(self) -> None:
        """Fires when stream ends or when exception is thrown"""
        detalog.put({"log" : "on_end", "check" : "Fires when stream ends or when exception is thrown"}, expire_in=120) 
        self.done.set()

    @override
    async def on_event(self, event: AssistantStreamEvent) -> None:
        if event.event == "thread.run.requires_action":
            print("\nthread.run.requires_action > submit tool call")
            print(f"ARGS: {self.arguments}")
            detalog.put({"log" : "on_event", "check" : str(event)}, expire_in=120) 


    # from https://github.com/openai/openai-python/blob/main/helpers.md
    @override
    async def on_tool_call_created(self, tool_call: ToolCall):
        print(f"\nassistant > {tool_call.type}\n", flush=True)

    @override
    async def on_tool_call_delta(self, delta: ToolCallDelta, snapshot: ToolCall):
        
        detalog.put({"log" : "on_tool_call_delta", "check" : str(delta)}, expire_in=120) 
        if delta.type == "code_interpreter" and delta.code_interpreter:
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
            for output in delta.code_interpreter.outputs:
                if output.type == "logs":
                    print(f"\n{output.logs}", flush=True)
        elif delta.type == "function" and delta.function:
            if delta.function.arguments:
                print(delta.function.arguments, end="", flush=True)
            if delta.function.output:
                print(f"\n\noutput >", flush=True)
            if delta.function.output != None:
                for output in delta.function.output:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)
            else:
                print(f"\noutput is None", flush=True)
    
    @override
    async def on_tool_call_done(self, tool_call: ToolCall) -> None:
        detalog.put({"log" : "on_tool_call_done", "check" : str(tool_call)}, expire_in=120)        
        return

    async def aiter(self) -> AsyncIterator[str]:
        while not self.queue.empty() or not self.done.is_set():
            done, other = await asyncio.wait(
                [
                    asyncio.ensure_future(self.queue.get()),
                    asyncio.ensure_future(self.done.wait()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if other:
                other.pop().cancel()

            token_or_done = cast(Union[str, Literal[True]], done.pop().result())

            if token_or_done is True:
                break

            yield token_or_done
