import logging
import os
from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = create_app()

if __name__ == "__main__":
    # Debug mode enables the Werkzeug interactive debugger, which allows
    # arbitrary code execution from the browser if it's ever reachable
    # outside local development. Default to off; opt in explicitly.
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=5000, debug=debug)
