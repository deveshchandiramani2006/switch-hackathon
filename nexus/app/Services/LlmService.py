"""
Full BYOLLM router — 7 providers.
Interface: LLMClient(agent="sales", tenant_config=None).complete(prompt, json_mode, system)
Falls back to secondary provider on failure.
"""
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

PROVIDERS = {
    "anthropic": {"pkg": "anthropic",          "models": ["claude-sonnet-4-6", "claude-haiku-4-5"]},
    "openai":    {"pkg": "openai",              "models": ["gpt-4o", "gpt-4o-mini", "o1-mini"]},
    "google":    {"pkg": "google.generativeai", "models": ["gemini-1.5-pro", "gemini-2.0-flash"]},
    "mistral":   {"pkg": "mistralai",           "models": ["mistral-large-latest", "mistral-medium-latest"]},
    "groq":      {"pkg": "groq",                "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]},
    "cohere":    {"pkg": "cohere",              "models": ["command-r-plus", "command-r"]},
    "ollama":    {"local": True,                "models": ["mistral", "llama3.2", "phi3", "qwen2.5"]},
}

CLOUD_AGENTS = {"sales", "support", "geo_seo"}

_DEFAULT_PROVIDER_BY_AGENT = {
    "sales":    ("anthropic", os.getenv("LLM_MODEL", "claude-sonnet-4-6")),
    "support":  ("anthropic", os.getenv("LLM_MODEL", "claude-sonnet-4-6")),
    "geo_seo":  ("anthropic", os.getenv("LLM_MODEL", "claude-sonnet-4-6")),
    "blog":     (os.getenv("BLOG_LLM_PROVIDER", "ollama"),
                 os.getenv("BLOG_LLM_MODEL", "mistral")),
    "infra":    (os.getenv("INFRA_LLM_PROVIDER", "ollama"),
                 os.getenv("INFRA_LLM_MODEL", "phi3")),
    "cs":       ("anthropic", os.getenv("LLM_MODEL", "claude-sonnet-4-6")),
    "finance":  ("anthropic", os.getenv("LLM_MODEL", "claude-sonnet-4-6")),
    "default":  ("anthropic", os.getenv("LLM_MODEL", "claude-sonnet-4-6")),
}


class LLMClient:
    def __init__(self, agent: str = "default", tenant_config: dict = None):
        self.agent = agent
        self.tenant_config = tenant_config or {}

        provider, model = self._resolve_provider_model()
        self.provider = provider
        self.model = model

        fallback_cfg = self.tenant_config.get("llm", {}).get("formatter", {}).get("fallback", {})
        self.fallback_provider = fallback_cfg.get("provider", None)
        self.fallback_model    = fallback_cfg.get("model", None)

    def _resolve_provider_model(self):
        """Priority: tenant_config[agents][X] > tenant_config[agents][default] > env defaults."""
        tc_llm = self.tenant_config.get("llm", {})
        agent_key = self.agent + "_agent" if not self.agent.endswith("_agent") else self.agent
        agent_cfg = (
            tc_llm.get("agents", {}).get(agent_key)
            or tc_llm.get("agents", {}).get(self.agent)
            or tc_llm.get("agents", {}).get("default")
            or {}
        )
        if agent_cfg:
            provider = agent_cfg.get("provider", "anthropic")
            model    = agent_cfg.get("model", PROVIDERS.get(provider, {}).get("models", [""])[0])
            return provider, model

        return _DEFAULT_PROVIDER_BY_AGENT.get(
            self.agent,
            _DEFAULT_PROVIDER_BY_AGENT["default"]
        )

    def complete(self, prompt: str, json_mode: bool = False, system: str = None) -> str:
        """Route to correct provider, fall back on failure."""
        try:
            return self._dispatch(self.provider, self.model, prompt, json_mode, system)
        except Exception as e:
            logger.warning(f"LLM primary provider '{self.provider}' failed: {e}")
            if self.fallback_provider:
                try:
                    return self._dispatch(
                        self.fallback_provider, self.fallback_model,
                        prompt, json_mode, system
                    )
                except Exception as e2:
                    logger.error(f"LLM fallback provider '{self.fallback_provider}' also failed: {e2}")
            if self.provider != "ollama":
                try:
                    return self._ollama(prompt)
                except Exception:
                    pass
            raise

    def _dispatch(self, provider: str, model: str, prompt: str, json_mode: bool, system: str) -> str:
        if provider == "anthropic":
            return self._anthropic(prompt, json_mode, system, model)
        elif provider == "openai":
            return self._openai(prompt, json_mode, system, model)
        elif provider == "google":
            return self._google(prompt, json_mode, system, model)
        elif provider == "mistral":
            return self._mistral(prompt, json_mode, system, model)
        elif provider == "groq":
            return self._groq(prompt, json_mode, system, model)
        elif provider == "cohere":
            return self._cohere(prompt, json_mode, system, model)
        elif provider == "ollama":
            return self._ollama(prompt, model)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _anthropic(self, prompt: str, json_mode: bool, system: str, model: str = None) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        sys_msg = system or ("Reply with valid JSON only. No markdown, no explanation." if json_mode else None)
        kwargs = {}
        if sys_msg:
            kwargs["system"] = sys_msg
        msg = client.messages.create(
            model=model or self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return msg.content[0].text

    def _openai(self, prompt: str, json_mode: bool, system: str, model: str = None) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        elif json_mode:
            messages.append({"role": "system", "content": "Reply with valid JSON only. No markdown, no explanation."})
        messages.append({"role": "user", "content": prompt})

        kwargs = {"model": model or self.model, "messages": messages, "max_tokens": 2048}
        if json_mode and "o1" not in (model or self.model):
            kwargs["response_format"] = {"type": "json_object"}

        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    def _google(self, prompt: str, json_mode: bool, system: str, model: str = None) -> str:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        m = genai.GenerativeModel(model or self.model)
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"
        elif json_mode:
            full_prompt = f"Reply with valid JSON only. No markdown, no explanation.\n\n{prompt}"
        resp = m.generate_content(full_prompt)
        return resp.text

    def _mistral(self, prompt: str, json_mode: bool, system: str, model: str = None) -> str:
        from mistralai import Mistral
        client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        elif json_mode:
            messages.append({"role": "system", "content": "Reply with valid JSON only. No markdown, no explanation."})
        messages.append({"role": "user", "content": prompt})
        kwargs = {"model": model or self.model, "messages": messages, "max_tokens": 2048}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.complete(**kwargs)
        return resp.choices[0].message.content

    def _groq(self, prompt: str, json_mode: bool, system: str, model: str = None) -> str:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        elif json_mode:
            messages.append({"role": "system", "content": "Reply with valid JSON only. No markdown, no explanation."})
        messages.append({"role": "user", "content": prompt})
        kwargs = {"model": model or self.model, "messages": messages, "max_tokens": 2048}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    def _cohere(self, prompt: str, json_mode: bool, system: str, model: str = None) -> str:
        import cohere
        client = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        elif json_mode:
            messages.append({"role": "system", "content": "Reply with valid JSON only. No markdown, no explanation."})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat(
            model=model or self.model,
            messages=messages,
            max_tokens=2048
        )
        return resp.message.content[0].text

    def _ollama(self, prompt: str, model: str = None) -> str:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = requests.post(
            f"{base}/api/generate",
            json={"model": model or self.model, "prompt": prompt, "stream": False},
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["response"]
