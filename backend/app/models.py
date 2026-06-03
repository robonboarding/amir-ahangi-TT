from typing import List, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    use_search: bool = Field(default=True)


class Source(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    reply: str
    model: str
    sources: List[Source] = Field(default_factory=list)
