import logging
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAIError

from .azure_openai import generate_reply
from .config import get_settings
from .models import ChatRequest, ChatResponse, Source
from .rabobank_search import build_grounding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot.backend")

settings = get_settings()

GROUNDING_INSTRUCTION = (
    "Use the following up-to-date information from rabobank.nl to answer the customer's "
    "question. Base your answer on these sources and keep it concise. If the sources do "
    "not contain the answer, say so and suggest contacting Rabobank. Do not invent URLs.\n\n"
    "SOURCES:\n"
)

app = FastAPI(title="Chatbot Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _latest_user_text(messages: List[Dict[str, str]]) -> str:
    for message in reversed(messages):
        if message["role"] == "user":
            return message["content"]
    return ""


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

    messages = [message.model_dump() for message in request.messages]
    sources: List[dict] = []

    if request.use_search:
        query = _latest_user_text(messages)
        if query:
            context, sources = build_grounding(query)
            if context:
                grounding = {"role": "system", "content": GROUNDING_INSTRUCTION + context}
                messages = messages[:-1] + [grounding] + messages[-1:]

    try:
        reply = generate_reply(messages, request.temperature)
    except OpenAIError:
        logger.exception("Azure OpenAI request failed")
        raise HTTPException(status_code=502, detail="The language model request failed.")

    return ChatResponse(
        reply=reply,
        model=settings.azure_openai_deployment,
        sources=[Source(**source) for source in sources],
    )
