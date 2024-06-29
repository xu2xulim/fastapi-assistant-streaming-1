import asyncio

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.event_handler import EventHandler

import os
from deta import Deta
DETA_DATA_KEY = os.environ.get('DETA_DATA_KEY')
detalog = Deta(DETA_DATA_KEY).Base('deta_log')

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
    """
    async def handle_tool_outputs(self, thread_id, run_id, tool_outputs):
        async with self.client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=thread_id, 
            run_id=run_id, 
            tool_outputs=tool_outputs,
            event_handler=EventHandler()
        ) as stream:
            await stream.until_done()
    """
    async def run_stream(self, thread, stream_it: EventHandler ):

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



