import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CLOUD_AGENTS = {"sales", "support", "geo_seo"}


class LLMClient:
    def __init__(self, agent: str = "default"):
        self.agent = agent
        if agent in CLOUD_AGENTS:
            self.provider = "anthropic"
            self.model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
        else:
            self.provider = os.getenv("BLOG_LLM_PROVIDER", "ollama")
            self.model = os.getenv("BLOG_LLM_MODEL", "mistral")

    def complete(self, prompt: str, json_mode: bool = False) -> str:
        if self.provider == "anthropic":
            return self._claude(prompt, json_mode)
        return self._ollama(prompt)

    def _claude(self, prompt: str, json_mode: bool) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        system = "Reply with valid JSON only. No markdown, no explanation." if json_mode else None
        kwargs = {}
        if system:
            kwargs["system"] = system
        msg = client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return msg.content[0].text

    def _ollama(self, prompt: str) -> str:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = requests.post(
            f"{base}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["response"]
