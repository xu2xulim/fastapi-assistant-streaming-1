import asyncio
from typing import AsyncIterator, Literal, Union, cast

from openai import AsyncAssistantEventHandler
from openai.types.beta import AssistantStreamEvent
from typing_extensions import override
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta

import os
import json
import requests
import random
import string


from deta import Deta
DETA_DATA_KEY = os.environ.get('DETA_DATA_KEY')
detalog = Deta(DETA_DATA_KEY).Base('assistant')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')


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
        
            if event.data.required_action and event.data.required_action.type == 'submit_tool_outputs':
                tools_called = event.data.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                characters = string.ascii_letters
                for tx in tools_called :
                    tool_name = tx.function.name
                    tool_args = tx.function.arguments
                    if tool_name == "get_random_digit":
                        tool_output = random.randrange(10)
                    elif tool_name == "get_random_letters":
                        idx = json.loads(tool_args)['count']
                        tool_output = ""
                        for ix in range(idx):
                            tool_output = tool_output + random.choice(characters)
                        
                        detalog.put({"log" : "count and output", "check" : f"{idx} and {tool_output}"}, expire_in=120) 
                    else:
                        tool_output = "Dummy"
                    
                    tool_outputs.append({
                        "tool_call_id": tx.id,
                        "output" : str(tool_output)
                    })
                
                headers = {
                    "Content-Type": "application/json",
                    "OpenAI-Beta" : "assistants=v2",
                    "Authorization" : f"Bearer {OPENAI_API_KEY}"}
                
                res = requests.post(f"https://api.openai.com/v1/threads/{event.data.thread_id}/runs/{event.data.id}/submit_tool_outputs", json={"tool_outputs" : tool_outputs, "stream" : True}, headers=headers)
                detalog.put({"log" : "res_text", "check" : str(res.text)}, expire_in=120) 
                try:
                    if res.status_code == 200:
                        for ex in str(res.text).split("\n\n"):
                            if "thread.message.completed" in ex:
                                detalog.put({"log" : "thread.message.completed", "check" : str(ex)}, expire_in=120) 
                                found = json.loads(ex.split("\n")[1].split("data: ")[1])
                                self.queue.put_nowait(found['content'][0]['text']['value'])
                                break
                    else:
                        self.queue.put_nowait("Process did not complete successfully")
                except:
                    self.queue.put_nowait("Process did not complete successfully")
                

    # from https://github.com/openai/openai-python/blob/main/helpers.md
    @override
    async def on_tool_call_created(self, tool_call: ToolCall):

        print(f"\nassistant > {tool_call.type}\n", flush=True)

    @override
    async def on_tool_call_delta(self, delta: ToolCallDelta, snapshot: ToolCall):
         
        if delta.type == "code_interpreter" and delta.code_interpreter:
            detalog.put({"log" : "on_tool_call_delta", "check" : str(delta)}, expire_in=120) 
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
            for output in delta.code_interpreter.outputs:
                if output.type == "logs":
                    print(f"\n{output.logs}", flush=True)
        
        elif delta.type == "function" and delta.function:
            detalog.put({"log" : "on_tool_call_delta", "check" : str(delta)}, expire_in=120) 
        """
            if delta.function.arguments:
                print(f"\n\narguments {json.loads(delta.function.arguments)}", end="", flush=True)
            if delta.function.output:
                print(f"\n\noutput >", flush=True)
            if delta.function.output != None:
                for output in delta.function.output:
                    #if output.type == "logs":
                    print(f"\n{output.type}", flush=True)

            else:
                print(f"\noutput is None", flush=True)
        """
    #@override
    #async def on_tool_call_done(self, tool_call: ToolCall) -> None:
        #detalog.put({"log" : "on_tool_call_done", "check" : str(tool_call)}, expire_in=120)        
        #return

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
