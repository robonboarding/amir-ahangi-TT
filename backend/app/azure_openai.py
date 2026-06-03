from functools import lru_cache
from typing import Dict, List

from openai import AzureOpenAI

from .config import get_settings


@lru_cache
def get_client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def generate_reply(messages: List[Dict[str, str]], temperature: float) -> str:
    settings = get_settings()
    completion = get_client().chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        temperature=temperature,
    )
    return completion.choices[0].message.content or ""
