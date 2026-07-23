from datetime import datetime, timezone
from time import monotonic

from flask import Flask, g, jsonify, request

import app.config as config
import app.db as db


def create_app():
    app = Flask(__name__)

    config_obj = config.load_config()
    db.init_db(config_obj.mongo_uri, config_obj.mongo_db)

    # ------------------------------------------------------------------
    # Health endpoint
    # ------------------------------------------------------------------

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # ------------------------------------------------------------------
    # Redirect blueprint
    # ------------------------------------------------------------------

    from app.routes import bp as redirect_bp
    app.register_blueprint(redirect_bp)

    # ------------------------------------------------------------------
    # Before request: record start time and client IP
    # ------------------------------------------------------------------

    @app.before_request
    def record_start():
        g.start_time = monotonic()

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            g.client_ip = forwarded_for.split(",")[0].strip()
        else:
            g.client_ip = request.remote_addr

    # ------------------------------------------------------------------
    # After request: write analytics log entry
    # ------------------------------------------------------------------

    @app.after_request
    def write_request_log(response):
        try:
            response_time_ms = round((monotonic() - g.start_time) * 1000)

            view_args = request.view_args or {}
            language = view_args.get("language")
            symbol = view_args.get("symbol")

            db.log_request({
                "timestamp": datetime.now(timezone.utc),
                "ip": getattr(g, "client_ip", request.remote_addr),
                "language": language,
                "symbol": symbol,
                "status_code": response.status_code,
                "response_time_ms": response_time_ms,
            })
        except Exception:
            app.logger.exception("Failed to write request log")

        return response

    return app
