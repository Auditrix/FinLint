"""The small Groq adapter used by both agents."""

import os

from dotenv import load_dotenv


def groq_completion(model: str):
    """Return a function that sends system and user text to a chosen model."""
    load_dotenv()
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("Set GROQ_API_KEY in .env before using Groq")
    if not model.strip():
        raise ValueError("Choose a Groq model name")
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("Install the project's groq dependency before calling Groq") from exc
    client = Groq(api_key=key)

    def complete(system: str, user: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned no text")
        return content

    return complete
