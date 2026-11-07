import logging
import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def create_app() -> Flask:
    application = Flask(__name__)
    from routes.api import api_bp
    application.register_blueprint(api_bp)
    return application


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("MANAGEMENT_API_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
