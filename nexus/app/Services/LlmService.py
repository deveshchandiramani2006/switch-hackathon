"""
Full BYOLLM router - 7 providers.
Interface: LLMClient(agent="sales", tenant_config=None).complete(prompt, json_mode, system)
Falls back to secondary provider on failure.
"""
import os
import logging
import threading
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

class _CircuitBreaker:
    """Per-provider circuit breaker: CLOSED -> OPEN (after N failures) -> HALF_OPEN (after timeout)."""
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT  = 120  # seconds

    def __init__(self):
        self._state = {}  # provider -> {state, failures, opened_at}
        self._lock  = threading.Lock()

    def allow(self, provider: str) -> bool:
        import time
        with self._lock:
            s = self._state.get(provider, {"state": "closed", "failures": 0, "opened_at": 0.0})
            if s["state"] == "closed":
                return True
            if s["state"] == "open":
                if time.time() - s["opened_at"] > self.RECOVERY_TIMEOUT:
                    s["state"] = "half_open"
                    self._state[provider] = s
                    return True
                return False
            return True  # half_open - let one through

    def on_success(self, provider: str):
        with self._lock:
            self._state[provider] = {"state": "closed", "failures": 0, "opened_at": 0.0}

    def on_failure(self, provider: str):
        import time
        with self._lock:
            s = self._state.get(provider, {"state": "closed", "failures": 0, "opened_at": 0.0})
            s["failures"] = s.get("failures", 0) + 1
            if s["failures"] >= self.FAILURE_THRESHOLD or s["state"] == "half_open":
                s["state"]     = "open"
                s["opened_at"] = time.time()
                logger.warning(f"Circuit breaker OPEN for provider '{provider}'")
            self._state[provider] = s


_breaker = _CircuitBreaker()

CLOUD_AGENTS = {"sales", "support", "geo_seo"}

_DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")

_DEFAULT_PROVIDER_BY_AGENT = {
    "sales":    (os.getenv("SALES_LLM_PROVIDER", "ollama"),   os.getenv("SALES_LLM_MODEL",   _DEFAULT_OLLAMA_MODEL)),
    "support":  (os.getenv("SUPPORT_LLM_PROVIDER", "ollama"), os.getenv("SUPPORT_LLM_MODEL", _DEFAULT_OLLAMA_MODEL)),
    "geo_seo":  (os.getenv("GEOSEO_LLM_PROVIDER", "ollama"),  os.getenv("GEOSEO_LLM_MODEL",  _DEFAULT_OLLAMA_MODEL)),
    "blog":     (os.getenv("BLOG_LLM_PROVIDER", "ollama"),    os.getenv("BLOG_LLM_MODEL",    _DEFAULT_OLLAMA_MODEL)),
    "infra":    (os.getenv("INFRA_LLM_PROVIDER", "ollama"),   os.getenv("INFRA_LLM_MODEL",   _DEFAULT_OLLAMA_MODEL)),
    "cs":       (os.getenv("CS_LLM_PROVIDER", "ollama"),      os.getenv("CS_LLM_MODEL",      _DEFAULT_OLLAMA_MODEL)),
    "finance":  (os.getenv("FINANCE_LLM_PROVIDER", "ollama"), os.getenv("FINANCE_LLM_MODEL", _DEFAULT_OLLAMA_MODEL)),
    "default":  (os.getenv("DEFAULT_LLM_PROVIDER", "ollama"), os.getenv("DEFAULT_LLM_MODEL", _DEFAULT_OLLAMA_MODEL)),
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

    def complete(self, prompt: str, json_mode: bool = False, system: str = None,
                tenant_id: str = None, client=None) -> str:
        """Route to correct provider with retry, feature gating, and fallback."""
        if os.getenv("LLM_MOCK_MODE", "").lower() == "true":
            _MOCK = {
                "sales": (
                    "Hi Vikram,\n\nFollowing up on our conversation — given your focus on streamlining "
                    "FinTech operations at scale, NEXUS could cut your team's coordination overhead significantly. "
                    "The automated deal → onboarding chain alone saves 2–3 hours per closed deal.\n\n"
                    "Happy to do a 20-minute walkthrough this week. Tuesday or Thursday work for you?\n\nBest,\nRavi"
                ),
                "support": (
                    "Severity: *P0 — Critical*\n\n"
                    "'All users affected' indicates a production-wide outage on the payment path. "
                    "Immediate escalation required. Blast radius: all Indian UPI transactions. "
                    "Recommend rollback to last stable deploy and notify CS within 15 minutes."
                ),
                "geo_seo": (
                    '{"score": 3, "gaps": ["No structured data markup", "Missing FAQ schema", '
                    '"No India-specific examples or case studies"], '
                    '"fixes": ["Add FAQ schema to top 3 pages", "Add 3 India startup case studies", '
                    '"Add HowTo structured data for onboarding flow"]}'
                ),
                "blog": (
                    "# Best CRM for Indian Startups in 2026: A Practical Guide\n\n"
                    "Indian B2B startups face a unique challenge: deal cycles average 45 days, reps work across "
                    "WhatsApp, email, and Slack, and most Western CRMs weren't built for this reality.\n\n"
                    "## What Indian Startups Actually Need\n"
                    "GST invoice generation. WhatsApp integration. INR pricing. Multilingual support. "
                    "Most US-first CRMs fail on at least two of these.\n\n"
                    "## Top Picks\n"
                    "For teams under 20 reps, the right CRM is one your team will actually use — "
                    "which means it needs to live where they already work: Slack."
                ),
                "cs": (
                    "*Health Score: 42/100 — At Risk*\n\n"
                    "• NPS dropped from 8 → 5 in the last 30 days\n"
                    "• Support tickets up 3× this month\n"
                    "• Last product login: 12 days ago\n"
                    "• Renewal in 10 days\n\n"
                    "*Recommended action:* Schedule EBR this week. Lead with the new reporting dashboard."
                ),
                "infra": "Service health check complete. All monitored endpoints responding within SLA.",
                "finance": "Invoice processed and logged. Revenue recognition complete for this quarter.",
            }
            return _MOCK.get(self.agent, _MOCK.get("sales", "Done."))

        import time

        # Feature gate check - blocks if tenant hit daily LLM limit
        if tenant_id and client:
            from app.Services.FeatureGateService import FeatureGateService
            if not FeatureGateService.gate_llm(tenant_id, client):
                raise RuntimeError("LLM daily limit reached for this tenant")

        # Primary provider with exponential backoff (3 attempts: 1s, 2s, 4s)
        last_exc = None
        for attempt in range(3):
            try:
                return self._dispatch(self.provider, self.model, prompt, json_mode, system)
            except Exception as e:
                last_exc = e
                if attempt < 2:
                    wait = 2 ** attempt  # 1s then 2s
                    logger.warning(f"LLM attempt {attempt + 1} failed ({e}), retrying in {wait}s")
                    time.sleep(wait)

        logger.warning(f"LLM primary provider '{self.provider}' failed after 3 attempts: {last_exc}")

        # Configured fallback provider
        if self.fallback_provider:
            for attempt in range(2):
                try:
                    return self._dispatch(
                        self.fallback_provider, self.fallback_model,
                        prompt, json_mode, system
                    )
                except Exception as e:
                    if attempt == 0:
                        time.sleep(1)
                    logger.error(f"LLM fallback provider '{self.fallback_provider}' attempt {attempt + 1} failed: {e}")

        # Last resort: local Ollama
        if self.provider != "ollama":
            try:
                return self._ollama(prompt)
            except Exception as e:
                logger.error(f"Ollama last-resort also failed: {e}")

        raise last_exc

    def _dispatch(self, provider: str, model: str, prompt: str, json_mode: bool, system: str) -> str:
        if not _breaker.allow(provider):
            raise RuntimeError(f"Circuit breaker OPEN for '{provider}' - skipping to fallback")
        try:
            result = self._route(provider, model, prompt, json_mode, system)
            _breaker.on_success(provider)
            return result
        except Exception as e:
            _breaker.on_failure(provider)
            raise

    def _route(self, provider: str, model: str, prompt: str, json_mode: bool, system: str) -> str:
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


import re

def md_to_slack(text: str) -> str:
    """Convert LLM markdown output to Slack mrkdwn."""
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'^#{1,3}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.MULTILINE)
    return text.strip()
