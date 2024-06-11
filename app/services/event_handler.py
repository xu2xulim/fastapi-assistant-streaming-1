import asyncio
from typing import AsyncIterator, Literal, Union, cast

from openai import AsyncAssistantEventHandler
from openai.types.beta import AssistantStreamEvent
from typing_extensions import override
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta

from app.core.config import settings

import os
import json
import requests
import random
import string


from deta import Deta
DETA_DATA_KEY = os.environ.get('DETA_DATA_KEY')
detalog = Deta().Base('deta_log')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

async def parse_email(self, emailplaintext):
    sub1 = settings.EMAIL_SUBSTRING_START
    sub2 = settings.EMAIL_SUBSTRING_END

    # getting index of substrings
    idx1 = emailplaintext.index(sub1)
    idx2 = emailplaintext.index(sub2)

    res = ''
    # getting elements in between
    for idx in range(idx1 + len(sub1) + 1, idx2):
        res = res + emailplaintext[idx]

    idx3 = res.index("\n")

    pfx_embed = sub1[:sub1.index(" ")+1]

    return res.split("\n")[0], res[idx3+1:].replace(pfx_embed, "")

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
                for tx in tools_called :
                    tool_name = tx.function.name
                    tool_args = tx.function.arguments
                    if tool_name == "parse_email":
                        tool_output = parse_email(tool_args.emailplaintext)
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
                
                res = requests.post(f"https://api.openai.com/v1/threads/{event.data.thread_id}/runs/{event.data.id}/submit_tool_outputs", json={"tool_outputs" : tool_outputs, "stream" : True}, headers=headers)
                detalog.put({"checkpoint" : "res_text", "value" : str(res.text)}, expire_in=120) 
                try:
                    if res.status_code == 200:
                        for ex in str(res.text).split("\n\n"):
                            if "thread.message.completed" in ex:
                                
                                found = json.loads(ex.split("\n")[1].split("data: ")[1])
                                #detalog.put({"checkpoint" : "event data" , "value" : found['content'][0]['text']['value']}, expire_in=120) 
                                textvalue = found['content'][0]['text']['value']
                                if textvalue is not None and textvalue != "":
                                    self.queue.put_nowait(textvalue)      
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

        #detalog.put({"checkpoint" : "on_tool_call_delta", "value" : str(delta)}, expire_in=120)
         
        if delta.type == "code_interpreter" and delta.code_interpreter:
            #detalog.put({"checkpoint" : "code_interpreter on_tool_call_delta", "value" : str(delta)}, expire_in=120) 
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
            if delta.code_interpreter.outputs != None:
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)
        
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
