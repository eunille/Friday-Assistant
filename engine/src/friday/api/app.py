"""FastAPI app: the desktop window's only way to talk to the engine.

Runs on 127.0.0.1. Every route except /health needs the launch token, which
the desktop app generates and passes to the engine when it starts it.

  GET  /health            is the engine up
  GET  /status            what Friday is doing right now
  GET  /models            model sources and the free models available
  POST /command           act on typed text, as if it had been spoken
  POST /activate          start listening without the wake word
  POST /stop              stop speaking
  GET  /approvals         questions waiting for a yes or no
  POST /approvals/{id}    answer one
  WS   /ws                live events: state, levels, speech, agent steps
"""
import asyncio
import hmac
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from friday import __version__
from friday.agent import router as command_router
from friday.agent.approvals import PendingApprovals
from friday.core.events import bus
from friday.core.log import log
from friday.core.status import status

# The Electron renderer (dev server or packaged app) and nothing else.
_ALLOWED_ORIGINS = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|app://.*|file://.*)$"
_command_lock = threading.Lock()


class Command(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ApprovalAnswer(BaseModel):
    allow: bool


def _run_command(text):
    """Imported lazily: loading the speech stack takes a while."""
    from friday.app import handle_text
    with _command_lock:
        handle_text(text)


def _speak_question(question):
    from friday.voice.stt import listen
    from friday.voice.tts.speaker import speak
    speak(question)
    return listen()


def create_app(token=None, voice=False, ask_by_voice=_speak_question) -> FastAPI:
    """token=None disables auth (tests, local development only)."""
    approvals = PendingApprovals(bus, ask_by_voice=ask_by_voice if voice else None)

    @asynccontextmanager
    async def lifespan(app):
        command_router.set_approval_channel(approvals.channel)
        if voice:
            from friday import app as voice_app
            voice_app.stop_requested.clear()
            threading.Thread(target=voice_app.run_voice_loop, name="voice-loop", daemon=True).start()
        yield
        command_router.set_approval_channel(None)
        if voice:
            from friday import app as voice_app
            voice_app.stop_requested.set()

    app = FastAPI(title="Friday engine", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origin_regex=_ALLOWED_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    def _token_ok(given):
        return token is None or (bool(given) and hmac.compare_digest(given, token))

    def authorised(authorization: str | None = Header(default=None),
                   token_param: str | None = Query(default=None, alias="token")):
        bearer = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
        if not (_token_ok(bearer) or _token_ok(token_param)):
            raise HTTPException(status_code=401, detail="Missing or wrong token")

    @app.get("/health")
    def health():
        return {"ok": True, "name": "friday", "version": __version__}

    @app.get("/status", dependencies=[Depends(authorised)])
    def get_status():
        return status.snapshot()

    @app.get("/models", dependencies=[Depends(authorised)])
    def models():
        from friday.core.config import get as cfg
        from friday.llm.factory import providers
        p = providers()
        free = []
        if p["openrouter"].available():
            try:
                free = p["openrouter"].free_models()
            except Exception as e:
                log.warning(f"Could not list free models: {e}")
        return {
            "source": (cfg("llm", "source") or "local"),
            "local": {"model": p["local"].model, "available": p["local"].available()},
            "openrouter": {"key_set": p["openrouter"].available(), "free_models": free},
        }

    @app.post("/command", dependencies=[Depends(authorised)])
    def command(body: Command):
        _run_command(body.text.strip())
        return {"ok": True, "response": status.snapshot()["response"]}

    @app.post("/activate", dependencies=[Depends(authorised)])
    def activate():
        from friday import app as voice_app
        voice_app.activated.set()
        return {"ok": True}

    @app.post("/stop", dependencies=[Depends(authorised)])
    def stop_speaking():
        from friday.voice.audio import stop_playback
        stop_playback()
        return {"ok": True}

    @app.get("/approvals", dependencies=[Depends(authorised)])
    def list_approvals():
        return approvals.pending()

    @app.post("/approvals/{request_id}", dependencies=[Depends(authorised)])
    def answer_approval(request_id: str, body: ApprovalAnswer):
        if not approvals.resolve(request_id, body.allow):
            raise HTTPException(status_code=404, detail="No such pending approval")
        return {"ok": True}

    @app.websocket("/ws")
    async def events(ws: WebSocket, token_param: str | None = Query(default=None, alias="token")):
        if not _token_ok(token_param):
            await ws.close(code=4401)
            return
        await ws.accept()
        loop = asyncio.get_running_loop()
        pending: asyncio.Queue = asyncio.Queue(maxsize=256)

        def offer(event):
            if pending.full():
                return  # a slow client loses level frames, never blocks the voice loop
            pending.put_nowait(event)

        unsubscribe = bus.subscribe(lambda event: loop.call_soon_threadsafe(offer, event))
        try:
            await ws.send_json({"type": "snapshot", **status.snapshot(),
                                "approvals": approvals.pending()})
            while True:
                await ws.send_json(await pending.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            unsubscribe()

    app.state.approvals = approvals
    return app
