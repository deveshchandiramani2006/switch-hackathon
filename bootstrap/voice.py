import logging
import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def create_app() -> Flask:
    application = Flask(__name__)
    from routes.voice import voice_bp
    application.register_blueprint(voice_bp)
    return application


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("VOICE_SERVER_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False)
