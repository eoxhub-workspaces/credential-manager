import logging
import http
import time

from fastapi import FastAPI, Request, Response
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


@app.middleware("http")
async def auth_check(request: Request, call_next):
    # this is not really an auth middleware, as auth is handled by the ingress
    # we just check if the user we get here is the correct one

    from my_credentials.views import current_namespace

    user = request.headers["X-Auth-Request-User"]
    if user != current_namespace():
        return Response(
            content=f"Access only allowed for user {current_namespace()}, not for {user}",
            status_code=http.HTTPStatus.FORBIDDEN,
        )

    return await call_next(request)


@app.get("/probe")
def probe():
    return {}


@app.middleware("http")
async def log_middle(request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    ignored_paths = ["/probe", "/metrics"]
    if request.url.path not in ignored_paths:
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
