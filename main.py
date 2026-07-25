import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import HOST, PORT
from database import (
    add_or_update_user,
    get_user_count,
    increment_tool_use,
    init_db,
)
from ads_integration import get_ad


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Telegram Tools Bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/user/track")
async def track_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if user_id:
        await add_or_update_user(
            user_id, data.get("username"), data.get("first_name")
        )
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.post("/api/tool/use")
async def tool_use(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if user_id:
        await increment_tool_use(user_id)
        return {"status": "ok"}
    return {"status": "error", "message": "user_id required"}


@app.get("/api/stats")
async def stats():
    count = await get_user_count()
    return {"total_users": count}


@app.get("/api/ad/{user_id}")
async def get_ad_for_user(user_id: int, language: str = "en"):
    ad = await get_ad(user_id, language)
    if ad:
        return ad
    return {"error": "No ad available"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
