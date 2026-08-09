from flask import Flask
from api.routes import api


def create_app():
    app = Flask(__name__)

    # Register API routes
    app.register_blueprint(api)

    @app.get("/")
    def health_check():
        return {
            "status": "ok",
            "service": "Cortex AI Autonomous Creator"
        }

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )