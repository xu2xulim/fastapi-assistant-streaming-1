import asyncio

from openai import AsyncOpenAI #, AssistantEventHandler

from app.core.config import settings
from app.services.event_handler import EventHandler

"""
class EventHandler(AssistantEventHandler):

    #@override
    async def on_event(self, event):
      # Retrieve events that are denoted with 'requires_action'
      # since these will have our tool_calls
      if event.event == 'thread.run.requires_action':
        run_id = event.data.id  # Retrieve the run ID from the event data
        self.handle_requires_action(event.data, run_id)
    
    async def handle_requires_action(self, data, run_id):
      tool_outputs = []
        
      for tool in data.required_action.submit_tool_outputs.tool_calls:
        if tool.function.name == "get_random_digit":
          tool_outputs.append({"tool_call_id": tool.id, "output": "7"})
        elif tool.function.name == "get_random_letter":
          tool_outputs.append({"tool_call_id": tool.id, "output": "X"})
        
      # Submit all tool_outputs at the same time
      self.submit_tool_outputs(tool_outputs, run_id)
 
    async def submit_tool_outputs(self, tool_outputs, run_id):
      # Use the submit_tool_outputs_stream helper
      with self.client.beta.threads.runs.submit_tool_outputs_stream(
        thread_id=self.current_run.thread_id,
        run_id=self.current_run.id,
        tool_outputs=tool_outputs,
        event_handler=EventHandler(),
      ) as stream:
        for text in stream.text_deltas:
          print(text, end="", flush=True)
        print()
"""
class AssistantService:
    client: AsyncOpenAI
    assistant_id: str

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.assistant_id = settings.OPENAI_ASSISTANT_ID

    async def get_assistant(self):
        assistant = await self.client.beta.assistants.retrieve(self.assistant_id)
        return assistant

    async def create_thread(self):
        thread = await self.client.beta.threads.create()
        return thread

    async def retrieve_thread(self, thread_id: str):
        thread = await self.client.beta.threads.retrieve(thread_id)
        return thread
    # delete thread
    async def delete_thread(self, thread_id: str):
        thread = await self.client.beta.threads.delete(thread_id)
        return thread

    async def create_message(self, thread_id, content):
        message = await self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )
        return message

    async def run_stream(self, thread, stream_it: EventHandler):
        async with self.client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=self.assistant_id,
            event_handler=stream_it,
        ) as stream:
            await stream.until_done()

    async def create_gen(self, thread, stream_it: EventHandler):
        task = asyncio.create_task(self.run_stream(thread, stream_it))
        async for token in stream_it.aiter():
            yield token
        await task


