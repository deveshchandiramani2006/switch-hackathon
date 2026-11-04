import os
import logging
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "base")

_whisper_model = None

AGENT_KEYWORDS = {
    "sales":   ["lead", "pipeline", "deal", "prospect", "follow up", "won", "lost", "crm"],
    "support": ["bug", "error", "crash", "broken", "down", "outage", "ticket"],
    "geo_seo": ["keyword", "seo", "ranking", "search", "geo", "content brief"],
    "blog":    ["draft", "blog", "approve", "publish", "content"],
    "infra":   ["deploy", "service", "health", "infrastructure", "monitor"],
    "cs":      ["customer", "renewal", "health score", "nps", "churn", "qbr"],
    "finance": ["invoice", "expense", "budget", "approve invoice", "payment"],
}


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        logger.info(f"Loading Whisper model: {WHISPER_MODEL_NAME}")
        _whisper_model = whisper.load_model(WHISPER_MODEL_NAME)
        logger.info("Whisper model loaded")
    return _whisper_model


def detect_agent(transcript: str) -> str:
    """Simple keyword-based agent routing from transcript."""
    t = transcript.lower()
    best_agent = "sales"
    best_score = 0
    for agent, keywords in AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in t)
        if score > best_score:
            best_score = score
            best_agent = agent
    return best_agent


def transcribe_audio_file(filepath: str) -> str:
    """Run Whisper on a saved audio file."""
    model = get_whisper_model()
    result = model.transcribe(filepath)
    return result.get("text", "").strip()


def save_transcription(agent: str, transcript: str, audio_file: str, tenant_id: str = "default"):
    """Log transcription to voice_transcriptions table."""
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO voice_transcriptions (tenant_id, agent, audio_file, transcript, processed_by)
                VALUES (%s, %s, %s, %s, 'whisper')
                """,
                (tenant_id, agent, audio_file, transcript)
            )
    except Exception as e:
        logger.warning(f"Failed to log transcription: {e}")
