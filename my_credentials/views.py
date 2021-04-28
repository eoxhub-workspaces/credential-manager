import base64
import collections
import logging

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client as k8s_client, config as k8s_config
from pydantic import BaseModel
from starlette.responses import RedirectResponse


from my_credentials import app

logger = logging.getLogger(__name__)


templates = Jinja2Templates(directory="templates")

LABEL_SELECTOR = "owner=edc-my-credentials"


@app.on_event("startup")
async def startup_load_k8s_config():
    try:
        k8s_config.load_kube_config()
    except Exception:
        # load_kube_config might throw anything :/
        k8s_config.load_incluster_config()


@app.get("/", response_class=HTMLResponse)
async def list_credentials(request: Request):

    secret_list: k8s_client.V1SecretList = (
        k8s_client.CoreV1Api().list_namespaced_secret(
            namespace=current_namespace(),
            label_selector=LABEL_SELECTOR,
        )
    )

    secrets_serialized = [serialize_secret(secret) for secret in secret_list.items]

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

    if is_new_credential:
        secret_data = {"name": "", "data": {}}
    else:
        secret: k8s_client.V1Secret = k8s_client.CoreV1Api().read_namespaced_secret(
            name=credential_name,
            namespace=current_namespace(),
        )
        secret_data = serialize_secret(secret)

    return templates.TemplateResponse(
        "credential_detail.html",
        {
            "request": request,
            "secret": secret_data,
            "is_new_credential": is_new_credential,
        },
    )


class CredentialsPayload(BaseModel):
    credentials_name: str = ""
    secret_value: list[str]
    secret_key: list[str]


@app.post("/credentials-detail/{credentials_name}", response_class=HTMLResponse)
@app.post("/credentials-detail/", response_class=HTMLResponse)
async def create_or_update(request: Request, credentials_name: str = ""):

    is_new_credential = not bool(credentials_name)

    form_data = await request.form()
    data = CredentialsPayload(
        credentials_name=credentials_name or form_data.get("credentials_name"),
        secret_value=form_data.getlist("secret_value"),
        secret_key=form_data.getlist("secret_key"),
    )

    do_action = (
        k8s_client.CoreV1Api().create_namespaced_secret
        if is_new_credential
        else k8s_client.CoreV1Api().patch_namespaced_secret
    )

    do_action(
        name=data.credentials_name,
        namespace=current_namespace(),
        body=k8s_client.V1Secret(
            data={
                key: base64.b64encode(value.encode()).decode()
                for key, value in zip(data.secret_key, data.secret_value)
            }
        ),
    )

    return RedirectResponse(url="/")


def serialize_secret(secret: k8s_client.V1Secret) -> dict:
    return {
        "name": secret.metadata.name,
        "data": B64DecodedAccessDict(secret.data),
    }


def current_namespace():
    # getting the current namespace like this is documented, so it should be fine:
    # https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/
    return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()


class B64DecodedAccessDict(collections.UserDict):
    def __getitem__(self, key) -> str:
        value = super().__getitem__(key)
        return base64.b64decode(value).decode()
