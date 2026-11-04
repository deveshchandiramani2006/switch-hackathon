import os
import tempfile
import logging
from flask import request, jsonify

from app.Services.VoiceService import (
    detect_agent, transcribe_audio_file, save_transcription, WHISPER_MODEL_NAME
)

logger = logging.getLogger(__name__)

AGENT_DISPLAY_MAP = {
    "sales":   "SalesAgent",
    "support": "SupportAgent",
    "geo_seo": "GeoSEOAgent",
    "blog":    "BlogAgent",
    "infra":   "InfraAgent",
    "cs":      "CSAgent",
    "finance": "FinanceAgent",
}


def health():
    return jsonify({"status": "ok", "model": WHISPER_MODEL_NAME})


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

    if agent == "auto" or not agent:
        agent = detect_agent(transcript)

    save_transcription(agent, transcript, audio_file.filename, tenant_id)

    return jsonify({
        "text":      transcript,
        "agent":     agent,
        "room_id":   room_id,
        "tenant_id": tenant_id
    })


def voice_command():
    """
    Transcribe + return a formatted Switch-ready message.
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

    agent_display  = AGENT_DISPLAY_MAP.get(agent, "SalesAgent")
    switch_message = f"@{agent_display} {transcript}"

    save_transcription(agent, transcript, audio_file.filename, tenant_id)

    return jsonify({
        "text":           transcript,
        "agent":          agent,
        "switch_message": switch_message,
        "room_id":        room_id,
        "tenant_id":      tenant_id
    })
