import os
import yaml
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Switch
    SWITCH_SERVER_URL = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")
    SWITCH_REGISTRATION_KEY = os.getenv("SWITCH_REGISTRATION_KEY", "")
    SWITCH_API_KEY = os.getenv("SWITCH_API_KEY", "")
    SWITCH_AGENT_ID = os.getenv("SWITCH_AGENT_ID", "")
    SWITCH_ROOM_ID = os.getenv("SWITCH_ROOM_ID", "")

    # Slack rooms
    SLACK_ROOM_SALES = os.getenv("SLACK_ROOM_SALES", "#nexus-sales")
    SLACK_ROOM_SUPPORT = os.getenv("SLACK_ROOM_SUPPORT", "#nexus-support")
    SLACK_ROOM_GROWTH = os.getenv("SLACK_ROOM_GROWTH", "#nexus-growth")
    SLACK_ROOM_CONTENT = os.getenv("SLACK_ROOM_CONTENT", "#nexus-content")
    SLACK_ROOM_DEVOPS = os.getenv("SLACK_ROOM_DEVOPS", "#nexus-devops")

    # LLM
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    BLOG_LLM_PROVIDER = os.getenv("BLOG_LLM_PROVIDER", "ollama")
    BLOG_LLM_MODEL = os.getenv("BLOG_LLM_MODEL", "mistral")
    INFRA_LLM_PROVIDER = os.getenv("INFRA_LLM_PROVIDER", "ollama")
    INFRA_LLM_MODEL = os.getenv("INFRA_LLM_MODEL", "phi3")

    # SEO
    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
    SEO_COUNTRY = os.getenv("SEO_COUNTRY", "IN")
    SEO_LANGUAGE = os.getenv("SEO_LANGUAGE", "en")
    GEO_SEO_MOCK_MODE = os.getenv("GEO_SEO_MOCK_MODE", "false").lower() == "true"

    # Blog
    BLOG_API_ENDPOINT = os.getenv("BLOG_API_ENDPOINT", "")
    BLOG_API_TOKEN = os.getenv("BLOG_API_TOKEN", "")
    BLOG_API_ADAPTER = os.getenv("BLOG_API_ADAPTER", "custom")
    BLOG_MOCK_MODE = os.getenv("BLOG_MOCK_MODE", "false").lower() == "true"

    # Whisper
    WHISPER_MODE = os.getenv("WHISPER_MODE", "local")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")

    # App
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ESCALATION_CHECK_MINUTES = int(os.getenv("ESCALATION_CHECK_MINUTES", "60"))
    GEO_SEO_INTERVAL_HOURS = int(os.getenv("GEO_SEO_INTERVAL_HOURS", "24"))

    @staticmethod
    def load_yaml(path=None):
        if path is None:
            path = os.path.join(os.path.dirname(__file__), "company.yaml")
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    @staticmethod
    def get_escalation_chain(agent: str):
        cfg = Config.load_yaml()
        return cfg.get("escalation_chains", {}).get(agent, {"levels": []})
