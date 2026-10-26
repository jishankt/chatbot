from flask import Flask
from app.config import Config
from app.api.routes import api_bp
from app.rag.ingest import ingest
from pathlib import Path


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure chunks exist
    chunks_path = Path(__file__).resolve().parent.parent / "data" / "chunks.json"
    if not chunks_path.exists():
        try:
            ingest()
        except Exception as e:
            app.logger.warning(f"Could not auto-ingest chunks: {e}")

    # Register blueprints
    app.register_blueprint(api_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
