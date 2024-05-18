import asyncio
from typing import AsyncIterator, Literal, Union, cast

from openai import AsyncOpenAI, AsyncAssistantEventHandler, AssistantStreamEvent
from openai.types.beta.threads import Text, TextDelta
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta
from openai.types.beta.threads import Message, MessageDelta
from openai.types.beta.threads.runs import ToolCall, RunStep
from typing_extensions import override


"""Async event handler that provides an async iterator."""


class EventHandler(AsyncAssistantEventHandler):
    openai_client: AsyncOpenAI
    queue: asyncio.Queue[str]
    done: asyncio.Event
    async def __init__(self, thread_id, assistant_id):
       super().__init__()
       self.queue = asyncio.Queue()
       self.done = asyncio.Event()
       self.output = None
       self.tool_id = None
       self.thread_id = thread_id
       self.assistant_id = assistant_id
       self.run_id = None
       self.run_step = None
       self.function_name = ""
       self.arguments = ""
      
    @override
    async def on_text_created(self, text) -> None:
       print(f"\nassistant on_text_created > ", end="", flush=True)

    @override
    async def on_text_delta(self, delta, snapshot):
       # print(f"\nassistant on_text_delta > {delta.value}", end="", flush=True)
       print(f"{delta.value}")

    @override
    async def on_end(self, ):
       print(f"\n end assistant > ",self.current_run_step_snapshot, end="", flush=True)

    @override
    async def on_exception(self, exception: Exception) -> None:
       """Fired whenever an exception happens during streaming"""
       print(f"\nassistant > {exception}\n", end="", flush=True)

    @override
    async def on_message_created(self, message: Message) -> None:
       print(f"\nassistant on_message_created > {message}\n", end="", flush=True)

    @override
    async def on_message_done(self, message: Message) -> None:
       print(f"\nassistant on_message_done > {message}\n", end="", flush=True)

    @override
    async def on_message_delta(self, delta: MessageDelta, snapshot: Message) -> None:
       # print(f"\nassistant on_message_delta > {delta}\n", end="", flush=True)
       pass

    async def on_tool_call_created(self, tool_call):
       # 4
       print(f"\nassistant on_tool_call_created > {tool_call}")
       self.function_name = tool_call.function.name       
       self.tool_id = tool_call.id
       print(f"\on_tool_call_created > run_step.status > {self.run_step.status}")
      
       print(f"\nassistant > {tool_call.type} {self.function_name}\n", flush=True)

       keep_retrieving_run = self.openai_client.beta.threads.runs.retrieve(
           thread_id=self.thread_id,
           run_id=self.run_id
       )

       while keep_retrieving_run.status in ["queued", "in_progress"]: 
           keep_retrieving_run = self.openai_client.beta.threads.runs.retrieve(
               thread_id=self.thread_id,
               run_id=self.run_id
           )
          
           print(f"\nSTATUS: {keep_retrieving_run.status}")      
      
    @override
    async def on_tool_call_done(self, tool_call: ToolCall) -> None:       
       keep_retrieving_run = self.openai_client.beta.threads.runs.retrieve(
           thread_id=self.thread_id,
           run_id=self.run_id
       )
      
       print(f"\nDONE STATUS: {keep_retrieving_run.status}")
      
       if keep_retrieving_run.status == "completed":
           all_messages = self.openai_client.beta.threads.messages.list(
               thread_id=self.thread_id
           )

           print(all_messages.data[0].content[0].text.value, "", "")
           return
      
       elif keep_retrieving_run.status == "requires_action":
           print("here you would call your function")

           if self.function_name == "example_blog_post_function":
               function_data = None
  
               self.output=function_data
              
               with self.openai_client.beta.threads.runs.submit_tool_outputs_stream(
                   thread_id=self.thread_id,
                   run_id=self.run_id,
                   tool_outputs=[{
                       "tool_call_id": self.tool_id,
                       "output": self.output,
                   }],
                   event_handler=EventHandler(self.thread_id, self.assistant_id)
               ) as stream:
                 stream.until_done()                       
           else:
               print("unknown function")
               return
      
    @override
    async def on_run_step_created(self, run_step: RunStep) -> None:
       # 2       
       print(f"on_run_step_created")
       self.run_id = run_step.run_id
       self.run_step = run_step
       print("The type ofrun_step run step is ", type(run_step), flush=True)
       print(f"\n run step created assistant > {run_step}\n", flush=True)

    @override
    async def on_run_step_done(self, run_step: RunStep) -> None:
       print(f"\n run step done assistant > {run_step}\n", flush=True)

    async def on_tool_call_delta(self, delta, snapshot): 
       if delta.type == 'function':
           # the arguments stream thorugh here and then you get the requires action event
           print(delta.function.arguments, end="", flush=True)
           self.arguments += delta.function.arguments
       elif delta.type == 'code_interpreter':
           print(f"on_tool_call_delta > code_interpreter")
           if delta.code_interpreter.input:
               print(delta.code_interpreter.input, end="", flush=True)
           if delta.code_interpreter.outputs:
               print(f"\n\noutput >", flush=True)
               for output in delta.code_interpreter.outputs:
                   if output.type == "logs":
                       print(f"\n{output.logs}", flush=True)
       else:
           print("ELSE")
           print(delta, end="", flush=True)

    @override
    async def on_event(self, event: AssistantStreamEvent) -> None:
       # print("In on_event of event is ", event.event, flush=True)

       if event.event == "thread.run.requires_action":
           print("\nthread.run.requires_action > submit tool call")
           print(f"ARGS: {self.arguments}")

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