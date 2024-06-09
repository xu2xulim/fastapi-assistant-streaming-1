from typing import Union
from fastapi import APIRouter, Body, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.dependencies.common import get_assistant_service
from app.services.assistant_service import AssistantService
from app.services.event_handler import EventHandler
from app.core.config import settings

from deta import Deta
import httpx


detalog = Deta().Base('deta_log')
oalog = Deta().Base('assistant')

router = APIRouter()

@router.get("/assistant")
async def get_assistant(
    assistant_service: AssistantService = Depends(get_assistant_service),
):
    return await assistant_service.get_assistant()

@router.post("/assistant/threads")
async def post_thread(
    assistant_service: AssistantService = Depends(get_assistant_service),
):
    thread = await assistant_service.create_thread()

    oalog.put({"thread_id" : thread.id})

    return {"data": thread}

class thread(BaseModel):
    thread_id: str

@router.delete("/assistant/threads")
async def delete_thread(
    query: thread = Body(...),
    assistant_service: AssistantService = Depends(get_assistant_service),
):
    thread = await assistant_service.delete_thread(query.thread_id)

    return {"data": thread}


class Query(BaseModel):
    text: str
    thread_id: str
#
@router.post("/assistant/chat")
async def chat(
    query: Query = Body(...),
    assistant_service: AssistantService = Depends(get_assistant_service)
):
    thread = await assistant_service.retrieve_thread(query.thread_id)

    await assistant_service.create_message(thread.id, query.text)
    detalog.put({"checkpoint" : "assistant", "text" : query.text, "thread_id" : query.thread_id}, expire_in=120)
    stream_it = EventHandler()
    gen = assistant_service.create_gen(thread, stream_it)
    
    return StreamingResponse(gen, media_type="text/event-stream")


@router.get("/endpoint/files")
async def list_files():

    headers = {"Authorization" : f"Bearer {settings.OPENAI_API_KEY}"}

    data = httpx.get(f"https://api.openai.com/v1/files", headers=headers).raise_for_status().json()

    return data
    

@router.get("/endpoint/file/{id}")
async def receive_file(
    background_tasks: BackgroundTasks,
    id:str
    ):

    
    headers = {"Authorization" : f"Bearer {settings.OPENAI_API_KEY}"}

    data = httpx.get(f"https://api.openai.com/v1/files/{id}", headers=headers).raise_for_status().json()
    
    filename = data['filename'].split("/")[-1]

    ext = filename.split(".")[-1]
    if ext in ['pdf', 'csv', 'png'] :
        pass
    else:
        return JSONResponse(content={"result" : f"Filetype {ext} is not supported"})
   
    client = httpx.AsyncClient()
    req = client.build_request("GET",f"https://api.openai.com/v1/files/{id}/content", headers=headers)
    r = await client.send(req, stream=True)
 
    headers={'Content-Disposition': f'attachment; filename={filename}'}
    detalog.put({"checkpoint" : "r", "log" : str(r)}, expire_in=120)
    
    if ext == 'pdf':
        return StreamingResponse(r.aiter_bytes(), background=background_tasks.add_task(r.aclose),headers=headers, media_type="application/pdf")
    elif ext == 'csv':
        return StreamingResponse(r.aiter_bytes(), background=background_tasks.add_task(r.aclose),headers=headers, media_type="text/csv")
    elif ext == 'png':
        return StreamingResponse(r.aiter_bytes(), background=background_tasks.add_task(r.aclose),headers=headers, media_type="image/png")
    elif ext in ['jpg', 'jpeg']:
        return StreamingResponse(r.aiter_bytes(), background=background_tasks.add_task(r.aclose),headers=headers, media_type="image/jpeg")
    else:
        return JSONResponse(content={"result" : f"Filetype {ext} is not supported "})