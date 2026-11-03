"""
Voice Server — Flask app for audio transcription via OpenAI Whisper.
Accepts audio uploads and returns transcripts routed to appropriate agents.

Endpoints:
  GET  /health              — liveness check
  POST /transcribe          — multipart audio upload → transcript
  POST /voice-command       — transcribe + format as Switch message
"""
import os
import tempfile
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "base")

# Lazy-load Whisper model on first use to speed startup
_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        logger.info(f"Loading Whisper model: {WHISPER_MODEL_NAME}")
        _whisper_model = whisper.load_model(WHISPER_MODEL_NAME)
        logger.info("Whisper model loaded")
    return _whisper_model


AGENT_KEYWORDS = {
    "sales":   ["lead", "pipeline", "deal", "prospect", "follow up", "won", "lost", "crm"],
    "support": ["bug", "error", "crash", "broken", "down", "outage", "ticket"],
    "geo_seo": ["keyword", "seo", "ranking", "search", "geo", "content brief"],
    "blog":    ["draft", "blog", "approve", "publish", "content"],
    "infra":   ["deploy", "service", "health", "infrastructure", "monitor"],
    "cs":      ["customer", "renewal", "health score", "nps", "churn", "qbr"],
    "finance": ["invoice", "expense", "budget", "approve invoice", "payment"],
}


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


def save_to_db(agent: str, transcript: str, audio_file: str, tenant_id: str = "default"):
    """Log transcription to voice_transcriptions table."""
    try:
        from shared.db import db_cursor
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


@app.route("/health")
def health():
    return jsonify({"status": "ok", "model": WHISPER_MODEL_NAME})


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """
    Accepts: multipart/form-data with 'audio' file + optional 'agent' and 'tenant_id' fields
    Returns: {"text": str, "agent": str, "room_id": str}
    """
    audio_file = request.files.get("audio")
    agent      = request.form.get("agent", "auto")
    tenant_id  = request.form.get("tenant_id", "default")
    room_id    = request.form.get("room_id", "")

    if not audio_file:
        return jsonify({"error": "No audio file provided"}), 400

    # Save to temp file
    suffix = os.path.splitext(audio_file.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_path = tmp.name
        audio_file.save(audio_path)

    try:
        transcript = transcribe_audio_file(audio_path)
        logger.info(f"Transcribed: {transcript[:100]}")
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass

    # Auto-detect agent if not specified
    if agent == "auto" or not agent:
        agent = detect_agent(transcript)

    save_to_db(agent, transcript, audio_file.filename, tenant_id)

    return jsonify({
        "text":    transcript,
        "agent":   agent,
        "room_id": room_id,
        "tenant_id": tenant_id
    })


@app.route("/voice-command", methods=["POST"])
def voice_command():
    """
    Convenience endpoint: transcribe + return a formatted Switch-ready message.
    The caller then sends this text to the appropriate agent room.

    Accepts: same as /transcribe
    Returns: {"text": str, "agent": str, "switch_message": str, "room_id": str}
    """
    audio_file = request.files.get("audio")
    agent      = request.form.get("agent", "auto")
    tenant_id  = request.form.get("tenant_id", "default")
    room_id    = request.form.get("room_id", "")

    if not audio_file:
        return jsonify({"error": "No audio file provided"}), 400

    suffix = os.path.splitext(audio_file.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_path = tmp.name
        audio_file.save(audio_path)

    try:
        transcript = transcribe_audio_file(audio_path)
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500
    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass

    if agent == "auto" or not agent:
        agent = detect_agent(transcript)

    # Format as a Switch @-mention
    agent_map = {
        "sales":   "SalesAgent",
        "support": "SupportAgent",
        "geo_seo": "GeoSEOAgent",
        "blog":    "BlogAgent",
        "infra":   "InfraAgent",
        "cs":      "CSAgent",
        "finance": "FinanceAgent",
    }
    agent_display = agent_map.get(agent, "SalesAgent")
    switch_message = f"@{agent_display} {transcript}"

    save_to_db(agent, transcript, audio_file.filename, tenant_id)

    return jsonify({
        "text":           transcript,
        "agent":          agent,
        "switch_message": switch_message,
        "room_id":        room_id,
        "tenant_id":      tenant_id
    })


if __name__ == "__main__":
    port = int(os.getenv("VOICE_SERVER_PORT", "5001"))
    logger.info(f"Voice server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
