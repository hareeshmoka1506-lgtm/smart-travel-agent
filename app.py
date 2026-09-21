import os
import sys
import json
import uuid
from pathlib import Path

_wwwroot = Path(__file__).resolve().parent
for _candidate in [_wwwroot / ".python_packages" / "lib" / "site-packages", *_wwwroot.glob("antenv/lib/python*/site-packages")]:
    if _candidate.is_dir():
        sys.path.insert(0, str(_candidate))

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Any


app = FastAPI(title="Agentic Travel Planner")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = None

def get_agent():
    global _agent
    if _agent is None:
        from agent import travel_agent
        _agent = travel_agent
    return _agent

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None

class ToolExecution(BaseModel):
    tool: str
    input: Any
    output: Any

class ChatResponse(BaseModel):
    thread_id: str
    response: str
    tools_used: List[ToolExecution]

static_dir = os.path.join(os.path.dirname(__file__), "static")

@app.get("/", response_class=HTMLResponse)
def read_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Agentic Travel Planner is Running</h1>")

@app.get("/style.css")
def read_css():
    css_path = os.path.join(static_dir, "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS not found")

@app.get("/app.js")
def read_js():
    js_path = os.path.join(static_dir, "app.js")
    if os.path.exists(js_path):
        with open(js_path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="JS not found")

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "travel-agent-mcp"}

def extract_text(content) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text") or "")
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
        return "".join(parts)
    return str(content)


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    from langchain_core.messages import HumanMessage

    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [HumanMessage(content=req.message)]}
    agent_instance = get_agent()

    async def event_generator():
        yield sse({"type": "init", "thread_id": thread_id})
        started_tools = set()
        try:
            async for item in agent_instance.astream(
                inputs,
                config=config,
                stream_mode=["messages", "updates"],
            ):
                mode, chunk = item if isinstance(item, tuple) and len(item) == 2 else ("messages", item)

                if mode == "messages":
                    msg, meta = chunk if isinstance(chunk, tuple) else (chunk, {})
                    node = (meta or {}).get("langgraph_node", "")
                    if node and node not in ("agent", "model"):
                        continue

                    for tc in getattr(msg, "tool_call_chunks", None) or []:
                        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                        if name and name not in started_tools:
                            started_tools.add(name)
                            yield sse({"type": "tool_start", "tool": name})

                    text = extract_text(getattr(msg, "content", ""))
                    if text:
                        yield sse({"type": "token", "content": text})

                elif mode == "updates" and isinstance(chunk, dict) and "tools" in chunk:
                    update = chunk.get("tools") or {}
                    messages = update.get("messages") if isinstance(update, dict) else []
                    for tm in messages or []:
                        name = getattr(tm, "name", None) or "tool"
                        yield sse({"type": "tool_end", "tool": name})

            yield sse({"type": "done"})
        except Exception as e:
            yield sse({"type": "error", "error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    agent_instance = get_agent()

    try:
        inputs = {"messages": [HumanMessage(content=req.message)]}
        result = await agent_instance.ainvoke(inputs, config=config)

        messages = result.get("messages", [])
        final_answer = ""
        tools_used = []

        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_answer = msg.content
                break

        for i, msg in enumerate(messages):
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tool_name = tc.get("name")
                    tool_args = tc.get("args")
                    tool_id = tc.get("id")
                    tool_output = None
                    for follow_msg in messages[i+1:]:
                        if isinstance(follow_msg, ToolMessage) and getattr(follow_msg, "tool_call_id", None) == tool_id:
                            tool_output = follow_msg.content
                            break
                    tools_used.append(ToolExecution(
                        tool=tool_name,
                        input=tool_args,
                        output=tool_output
                    ))

        return ChatResponse(
            thread_id=thread_id,
            response=final_answer,
            tools_used=tools_used
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

try:
    from a2wsgi import ASGIMiddleware
    wsgi_app = ASGIMiddleware(app)
    application = wsgi_app
except Exception:
    wsgi_app = app
    application = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
