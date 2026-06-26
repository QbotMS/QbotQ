"""qbot-web - publiczny serwis HTML (Faza 1: statyczna strona)."""
import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

WEB_ROOT = os.environ.get("QBOT_WEB_ROOT", "/opt/qbot/web/public")
HOST = os.environ.get("QBOT_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("QBOT_WEB_PORT", "30181"))

app = FastAPI(title="qbot-web", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
