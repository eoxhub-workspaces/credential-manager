import logging
import time

from fastapi import FastAPI, Request
from starlette_exporter import PrometheusMiddleware, handle_metrics

app = FastAPI()

app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)

if __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message).1000s",
        level=gunicorn_logger.level,
        handlers=gunicorn_logger.handlers,
    )

INFRASTRUCTURE_VIEWS = ["/probe", "/metrics"]


@app.get("/probe")
def probe():
    return {}


@app.middleware("http")
async def log_middle(request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    if request.url.path not in INFRASTRUCTURE_VIEWS:
        # NOTE: swagger validation failures prevent log_start_time from running
        duration = time.time() - start_time
        logging.info(
            f"{request.method} {request.url} "
            f"duration:{duration * 1000:.2f}ms "
            f"content_length:{response.headers.get('content-length')} "
            f"status:{response.status_code}"
        )

    return response


import my_credentials.views  # noqa
