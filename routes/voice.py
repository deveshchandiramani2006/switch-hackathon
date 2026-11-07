from flask import Blueprint
from app.Http.Controllers.VoiceController import health, transcribe, voice_command

voice_bp = Blueprint("voice", __name__)

voice_bp.add_url_rule("/health",        view_func=health,         methods=["GET"])
voice_bp.add_url_rule("/transcribe",    view_func=transcribe,     methods=["POST"])
voice_bp.add_url_rule("/voice-command", view_func=voice_command,  methods=["POST"])
