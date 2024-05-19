import asyncio
from typing import AsyncIterator, Literal, Union, cast

from openai import AsyncAssistantEventHandler
from typing_extensions import override
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
        self.done.set()
    
    @override
    async def on_event(self, event):
        #detalog.put({"log" : "on_event", "check" : str(event)}, expire_in=120)
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == 'thread.run.requires_action':
            detalog.put({"log" : "thread.run.requires_action", "check" : str(event.data.thread_id)}, expire_in=120)
            x_run_id = event.data.id  # Retrieve the run ID from the event data
            x_thread_id = event.data.thread_id
            #handle_requires_action(event.data, run_id)


    #def handle_requires_action(self, data, run_id):
            #detalog.put({"log" : "handle_requires_action", "check" : "I am here"}, expire_in=120)
            tool_outputs = []
        
            for tool in event.data.required_action.submit_tool_outputs.tool_calls:
                if tool.function.name == "get_random_digit":
                    tool_outputs.append(json.dumps({"tool_call_id": tool.id, "output": "57"}))
                elif tool.function.name == "get_random_letter":
                    tool_outputs.append(json.dumps({"tool_call_id": tool.id, "output": "X"}))
        
    # Submit all tool_outputs at the same time
    #submit_tool_outputs(tool_outputs, run_id)

    #def submit_tool_outputs(self, tool_outputs, run_id):    
            #detalog.put({"log" : "submit_tool_outputs", "check" : tool_outputs}, expire_in=120)
    # Use the submit_tool_outputs_stream helper
            with self.client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=x_thread_id,
                run_id=x_run_id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
            ) as stream:
                for text in stream.text_deltas:
                    print(text, end="", flush=True)
            
            detalog.put({"log" : "End of submit_tool_outputs", "check" : tool_outputs}, expire_in=120)
 
    async def on_tool_call_created(self, tool_call):
        detalog.put({"log" : "on_tool_call_created", "check" : "OK"}, expire_in=120)
  
    async def on_tool_call_delta(self, delta, snapshot):
        #detalog.put({"log" : "on_tool_call_delta", "check" : delta.type}, expire_in=120)
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)
                    else:
                        print(f"\nOutput Type: {output.type}", flush=True)
        elif delta.type == 'function':
            #detalog.put({"log" : "on_tool_call_delta - input", "check" : delta.function.arguments}, expire_in=120)
            #.put({"log" : "on_tool_call_delta - output", "check" : delta.function.output}, expire_in=120)
            print(f"Delta Type: {delta.type}", flush=True)
        else:
            print(f"Delta Type: {delta.type} not supported", flush=True)

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
