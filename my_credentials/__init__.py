import logging
import time
from logging.config import dictConfig
from fastapi import FastAPI, Request
from starlette_exporter import PrometheusMiddleware, handle_metrics


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message).1000s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        # Your custom app logger
        "app.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Silence Uvicorn/Gunicorn standard access logs
        "uvicorn.access": {"handlers": [], "level": "ERROR", "propagate": False},
        "gunicorn.access": {"handlers": [], "level": "ERROR", "propagate": False},
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}

dictConfig(LOGGING_CONFIG)

app = FastAPI()
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)

access_logger = logging.getLogger("app.access")
INFRASTRUCTURE_VIEWS = ["/probe", "/metrics"]


@app.middleware("http")
async def log_middle(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)

    if request.url.path not in INFRASTRUCTURE_VIEWS:
        duration = (time.time() - start_time) * 1000
        access_logger.info(
            f"{request.method} {request.url.path} "
            f"duration:{duration:.2f}ms "
            f"status:{response.status_code}"
        )
    return response


@app.get("/probe")
def probe():
    return {}

import my_credentials.views  # noqa