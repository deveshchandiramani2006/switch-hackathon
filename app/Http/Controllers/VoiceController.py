import os
import uuid
import tempfile
import logging
import requests
from flask import request, jsonify

from app.Services.VoiceService import (
    detect_agent, transcribe_audio_file, save_transcription, WHISPER_MODEL_NAME
)

logger = logging.getLogger(__name__)

SWITCH_URL = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")

AGENT_DISPLAY_MAP = {
    "sales":   "SalesAgent",
    "support": "SupportAgent",
    "geo_seo": "GeoSEOAgent",
    "blog":    "BlogAgent",
    "infra":   "InfraAgent",
    "cs":      "CSAgent",
    "finance": "FinanceAgent",
}

AGENT_ROOM_ENV = {
    "sales":   "SWITCH_ROOM_ID_SALES",
    "support": "SWITCH_ROOM_ID_SUPPORT",
    "geo_seo": "SWITCH_ROOM_ID_GROWTH",
    "blog":    "SWITCH_ROOM_ID_CONTENT",
    "infra":   "SWITCH_ROOM_ID_DEVOPS",
    "cs":      "SWITCH_ROOM_ID_CS",
    "finance": "SWITCH_ROOM_ID_FINANCE",
}


def _post_to_switch(agent_key: str, room_id: str, text: str):
    """Post transcribed voice command to Switch room if voice agent credentials are set."""
    agent_id = os.getenv("SWITCH_AGENT_ID_VOICE")
    api_key  = os.getenv("SWITCH_API_KEY_VOICE")
    if not agent_id or not api_key:
        logger.info("SWITCH_AGENT_ID_VOICE / SWITCH_API_KEY_VOICE not set - skipping Switch post")
        return False
    target_room = room_id or os.getenv(AGENT_ROOM_ENV.get(agent_key, "SWITCH_ROOM_ID_SALES"), "")
    if not target_room:
        logger.warning(f"No room ID for agent '{agent_key}' - cannot post to Switch")
        return False
    try:
        requests.post(
            f"{SWITCH_URL}/agents/{agent_id}/ops/post_message",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Switch-Connection-Id": str(uuid.uuid4()),
            },
            json={"room_id": target_room, "text": text},
            timeout=10,
        )
        logger.info(f"Voice command posted to Switch room {target_room}: {text[:80]}")
        return True
    except Exception as e:
        logger.error(f"Failed to post voice command to Switch: {e}")
        return False


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

    posted = _post_to_switch(agent, room_id, switch_message)

    return jsonify({
        "text":           transcript,
        "agent":          agent,
        "switch_message": switch_message,
        "room_id":        room_id,
        "tenant_id":      tenant_id,
        "posted_to_switch": posted,
    })
