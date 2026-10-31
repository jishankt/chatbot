from flask import Flask
from app.config import Config
from app.api.routes import api_bp
from app.rag.ingest import ingest
from pathlib import Path


def create_app(config_class=Config):
    from app.config import validate_config
    validate_config()

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

    # Trust reverse proxy headers (Nginx) for remote_addr, scheme, and host
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
