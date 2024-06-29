import asyncio
from typing import AsyncIterator, Literal, Union, cast

from openai import AsyncAssistantEventHandler
from openai.types.beta import AssistantStreamEvent
from typing_extensions import override
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta

from app.core.config import settings

import json
import httpx
import random
import string

import os
from deta import Deta
DETA_DATA_KEY = os.environ.get('DETA_DATA_KEY')
detalog = Deta(DETA_DATA_KEY).Base('deta_log')
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
        detalog.put({"checkpoint" : "on_end", "value" : "Fires when stream ends or when exception is thrown"}, expire_in=120) 
        self.done.set()
    
    @override
    async def on_event(self, event: AssistantStreamEvent) -> None:
        
        if event.event == "thread.run.requires_action":

            detalog.put({"checkpoint" : "required action", "value" : event.event, "event" : str(event)}, expire_in=120)
            
            if event.data.required_action and event.data.required_action.type == 'submit_tool_outputs':
                tools_called = event.data.required_action.submit_tool_outputs.tool_calls
                detalog.put({"checkpoint" : "tools called", "value" : str(tools_called)}, expire_in=120)
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
                        
                    #detalog.put({"checkpoint" : "count and output", "value" : f"{idx} and {tool_output}"}, expire_in=120) 
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
                
                try:
                    detalog.put({"checkpoint" : "before submit tool output", "value" : tool_outputs}, expire_in=120) 
                    #res = httpx.post(f"https://api.openai.com/v1/threads/{event.data.thread_id}/runs/{event.data.id}/submit_tool_outputs", json={"tool_outputs" : tool_outputs, "stream" : True}, headers=headers)
                    response_text = None
                    async with httpx.AsyncClient() as client:
                        req = client.build_request("POST", f"https://api.openai.com/v1/threads/{event.data.thread_id}/runs/{event.data.id}/submit_tool_outputs", json={"tool_outputs" : tool_outputs, "stream" : True}, headers=headers)
                        res = await client.send(req, stream=True)
        
                        byte_string = await res.aread()  # Read the response content
        
                        # Optionally, you might want to check the status code
                        if res.status_code == 200:
                            response_text = str(byte_string, encoding='utf-8')
                        else:
                            raise Exception(f"Request failed with status code {res.status_code}")
                    
                    detalog.put({"checkpoint" : "status code", "value" : res.status_code}, expire_in=120)
                    detalog.put({"checkpoint" : "res_text", "value" : response_text}, expire_in=120)

                    if res.status_code == 200 and response_text!=None:
                        self.done.clear()
                        events = [x.split("\n") for x in response_text.split("\n\n")]
                        events.reverse()
                        for ex in events:
                            if 'thread.message.completed' in ex[0]:
                                thread_msg = json.loads(ex[1].split('data:')[1].strip())
                                textvalue = thread_msg['content'][0]['text']['value']
                                detalog.put({"checkpoint" : "text value" , "value" : textvalue}, expire_in=120) 
                                if textvalue is not None and textvalue != "":
                                    self.queue.put_nowait(textvalue)
                                else:
                                    detalog.put({"checkpoint" : "null message"}, expire_in=120)
                                    self.queue.put_nowait("Received a null message from submit tool outputs")
                                break   
                    else:
                        self.queue.put_nowait("Submit tool outputs did not complete successfully")
                
                except:
                    self.queue.put_nowait("Error in handle tool outputs")
                
    
    # from https://github.com/openai/openai-python/blob/main/helpers.md
    @override
    async def on_tool_call_created(self, tool_call: ToolCall):

        print(f"\nassistant > {tool_call.type}\n", flush=True)

    @override
    async def on_tool_call_delta(self, delta: ToolCallDelta, snapshot: ToolCall):
         
        if delta.type == "code_interpreter" and delta.code_interpreter:
            
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
            if delta.code_interpreter.outputs != None:
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)
        
    #@override
    #async def on_tool_call_done(self, tool_call: ToolCall) -> None:
        #detalog.put({"checkpoint" : "on_tool_call_done", "value" : str(tool_call)}, expire_in=120)        
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
