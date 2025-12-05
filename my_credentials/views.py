import base64
import collections
import http
import logging

from fastapi import Request, Response, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel
from starlette.responses import RedirectResponse

from my_credentials import app

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

MY_SECRETS_LABEL_KEY = "owner"
MY_SECRETS_LABEL_VALUE = "edc-my-credentials"


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
            label_selector=f"{MY_SECRETS_LABEL_KEY}={MY_SECRETS_LABEL_VALUE}",
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
    credentials_name: str | None = ""
    secret_value: list[str]
    secret_key: list[str]


@app.post("/credentials-detail/{credentials_name}", response_class=HTMLResponse)
@app.post("/credentials-detail/", response_class=HTMLResponse)
async def create_or_update(request: Request, credentials_name: str = ""):
    form_data = await request.form(max_files=0)

    is_update = bool(credentials_name)
    credentials_name = (
        credentials_name or str(form_data.get("credentials_name")).strip()
    )
    secret_value = [str(sv) for sv in form_data.getlist("secret_value")]
    secret_key = [str(sk).strip() for sk in form_data.getlist("secret_key")]
    data = CredentialsPayload(
        credentials_name=credentials_name,
        secret_value=secret_value,
        secret_key=secret_key,
    )

    new_secret = k8s_client.V1Secret(
        metadata=k8s_client.V1ObjectMeta(
            name=data.credentials_name,
            labels={MY_SECRETS_LABEL_KEY: MY_SECRETS_LABEL_VALUE},
        ),
        data={
            key: base64.b64encode(value.encode()).decode()
            for key, value in zip(data.secret_key, data.secret_value)
        },
    )

    if is_update:
        existing_secret = ensure_secret_is_mine(credentials_name)
        # set keys to None for deletion
        new_secret.data = {k: None for k in (existing_secret.data or {})} | (
            new_secret.data or {}
        )
        k8s_client.CoreV1Api().patch_namespaced_secret(
            name=credentials_name,
            namespace=current_namespace(),
            body=new_secret,
        )
    else:
        try:
            k8s_client.CoreV1Api().create_namespaced_secret(
                namespace=current_namespace(),
                body=new_secret,
            )
        except ApiException:
            raise HTTPException(status_code=http.HTTPStatus.CONFLICT,
                                detail=f"CONFLICT: "
                                       f"There's already a credential "
                                       f"named '{data.credentials_name}'.")

    return RedirectResponse(
        # NOTE: ".." works also for updates because the url doesn't end in /
        url="..",
        status_code=http.HTTPStatus.FOUND,
    )


@app.delete("/credentials-detail/{credentials_name}")
def delete_credentials(credentials_name: str):  # , response_class=PlainTextResponse
    _ = ensure_secret_is_mine(credentials_name)
    k8s_client.CoreV1Api().delete_namespaced_secret(
        name=credentials_name,
        namespace=current_namespace(),
    )
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


def serialize_secret(secret: k8s_client.V1Secret) -> dict:
    return {
        "name": secret.metadata.name,
        "data": B64DecodedAccessDict(secret.data),
        "annotations": secret.metadata.annotations if secret.metadata.annotations else {},
    }


def current_namespace():
    # getting the current namespace like this is documented, so it should be fine:
    # https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/
    return open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()


class B64DecodedAccessDict(collections.UserDict):
    def __getitem__(self, key) -> str:
        value = super().__getitem__(key)
        return base64.b64decode(value).decode()


def ensure_secret_is_mine(credential_name: str) -> k8s_client.V1Secret:
    secret: k8s_client.V1Secret = k8s_client.CoreV1Api().read_namespaced_secret(
        name=credential_name,
        namespace=current_namespace(),
    )

    if secret.metadata.labels.get(MY_SECRETS_LABEL_KEY) != MY_SECRETS_LABEL_VALUE:
        raise HTTPException(status_code=http.HTTPStatus.FORBIDDEN)

    return secret
