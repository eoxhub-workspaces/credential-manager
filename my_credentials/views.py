import base64
import collections
import logging
import http
from typing import cast

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client as k8s_client, config as k8s_config
import kubernetes.client.rest


from my_credentials import app

logger = logging.getLogger(__name__)


templates = Jinja2Templates(directory="templates")

LABEL_SELECTOR = "owner=edc-my-credentials"


@app.on_event("startup")
async def startup_load_k8s_config():
    return
    try:
        k8s_config.load_kube_config()
    except Exception:
        # load_kube_config might throw anything :/
        k8s_config.load_incluster_config()


@app.get("/", response_class=HTMLResponse)
async def list_credentials(request: Request):

    # TODO: add label selector
    secret_list: k8s_client.V1SecretList = (
        k8s_client.CoreV1Api().list_namespaced_secret(
            namespace=current_namespace(),
            label_selector=LABEL_SELECTOR,
        )
    )

    secrets_serialized = [
        {
            "name": secret.metadata.name,
            "data": B64DecodedAccessDict(secret.data),
        }
        for secret in secret_list.items
    ]

    return templates.TemplateResponse(
        "credentials.html",
        {
            "request": request,
            "secrets": secrets_serialized,
        },
    )


@app.get("/credentials-detail/{credential_name}", response_class=HTMLResponse)
@app.get("/credentials-detail/", response_class=HTMLResponse)
async def credentials_detail(request: Request, credential_name: str = ""):
    is_new_credential = not bool(credential_name)

    secret = {"name": credential_name, "data": {"a": "b", "c": "d"}}

    return templates.TemplateResponse(
        "credential_detail.html",
        {
            "request": request,
            "secret": secret,
            "is_new_credential": is_new_credential,
        },
    )


@app.post("/credentials-detail/{credential_name}", response_class=HTMLResponse)
@app.post("/credentials-detail/", response_class=HTMLResponse)
async def create_or_udpate(request: Request, credential_name: str = ""):
    # credentials-name=asdf&secret_key=a&secret_value=b&secret_key=asdf&secret_value=d
    ...


def current_namespace():
    # getting the current namespace like this is documented, so it should be fine:
    # https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/
    return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()


class B64DecodedAccessDict(collections.UserDict):
    def __getitem__(self, key) -> str:
        value = super().__getitem__(key)
        return base64.b64decode(value).decode()


class SecretNotFound(RuntimeError):
    pass


def read_secret(name: str) -> k8s_client.V1Secret:
    try:
        return cast(
            k8s_client.V1Secret,
            k8s_client.CoreV1Api().read_namespaced_secret(
                name=name,
                namespace=current_namespace(),
            ),
        )
    except kubernetes.client.rest.ApiException as e:
        if e.status == http.HTTPStatus.NOT_FOUND:
            raise SecretNotFound(f"Secret {name} not found") from e
        else:
            raise
