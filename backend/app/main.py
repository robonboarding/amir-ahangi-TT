import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAIError

from .azure_openai import generate_reply
from .config import get_settings
from .models import ChatRequest, ChatResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot.backend")

settings = get_settings()

app = FastAPI(title="Chatbot Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "configured": settings.is_configured}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not settings.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Backend is not configured: AZURE_OPENAI_API_KEY is missing.",
        )

    payload = [message.model_dump() for message in request.messages]
    try:
        reply = generate_reply(payload, request.temperature)
    except OpenAIError:
        logger.exception("Azure OpenAI request failed")
        raise HTTPException(status_code=502, detail="The language model request failed.")

    return ChatResponse(reply=reply, model=settings.azure_openai_deployment)
