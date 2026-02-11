import base64
import collections
import http
import json
import logging
import os
import re
from typing import Dict, cast

from fastapi import File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
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


def get_secret_list() -> list:
    secret_list: k8s_client.V1SecretList = (
        k8s_client.CoreV1Api().list_namespaced_secret(
            namespace=current_namespace(),
            label_selector=f"{MY_SECRETS_LABEL_KEY}={MY_SECRETS_LABEL_VALUE}",
        )
    )

    return [serialize_secret(secret) for secret in secret_list.items]


@app.get("/", response_class=HTMLResponse)
async def list_credentials(request: Request):
    secrets_serialized = get_secret_list()

    return templates.TemplateResponse(
        "credentials.html",
        {
            "request": request,
            "secrets": secrets_serialized,
        },
    )


@app.get("/get-credentials")  # ?app=
async def list_credentials_api(app=None):
    secret_list = get_secret_list()
    opaque_secrets = [s for s in secret_list if s.get("type") == "key-value (Opaque)"]
    if not app:
        return opaque_secrets
    return [s for s in opaque_secrets if s.get("annotations").get(f"eoxhub-env-{app}")]


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

    secret_type = secret_data.get("type")
    if secret_type == "kubernetes.io/ssh-auth":
        template = "credential_ssh.html"
    elif secret_type == "kubernetes.io/dockerconfigjson":
        template = "credential_dockerconfigjson.html"

        data_map = cast(
            Dict[str, str], secret_data.get("data", {})
        )  # necessary for mypy
        cfg = data_map.get(".dockerconfigjson", "")
        secret_data_dict = json.loads(cfg)

        registry = list(secret_data_dict["auths"].keys())[0]
        user = secret_data_dict["auths"][registry].get("user", "")
        password = secret_data_dict["auths"][registry].get("password", "")
        auth = secret_data_dict["auths"][registry].get("auth", "")
        auth_decoded = base64.b64decode(auth.encode()).decode()
        secret_data["data"] = {
            "registry": registry,
            "user": user,
            "password": password,
            "auth": auth_decoded,
            ".dockerconfigjson": cfg,
        }
    else:
        template = "credential_opaque.html"

    if template:
        return templates.TemplateResponse(
            template,
            {"request": request, "secret": secret_data, "is_new_credential": False},
        )
    else:
        return RedirectResponse(
            url="..",
            status_code=http.HTTPStatus.NOT_FOUND,
        )


class CredentialsPayload(BaseModel):
    credentials_name: str | None = ""
    secret_value: list[str]
    secret_key: list[str]


@app.post("/credentials-detail/{credentials_name}", response_class=HTMLResponse)
@app.post("/credentials-detail/", response_class=HTMLResponse)
async def create_or_update(
    request: Request, credentials_name: str = "", file_content: str | None = None
):
    form_data = await request.form(max_files=0)

    is_update = bool(credentials_name)
    credentials_name = (
        credentials_name or str(form_data.get("credentials_name")).strip()
    )

    type = form_data.get("type", "")
    secret_metadata = k8s_client.V1ObjectMeta(
        name=credentials_name,
        labels={MY_SECRETS_LABEL_KEY: MY_SECRETS_LABEL_VALUE},
    )
    secret_data = {}
    if type == "kubernetes.io/ssh-auth":
        if file_content:
            private_key = file_content
        else:
            private_key = (
                str(form_data.get("privatekey", "")).rstrip("\n").replace("\r", "")
                + "\n"
            )

        if isinstance(private_key, str):
            secret_data = {
                "ssh-privatekey": base64.b64encode(private_key.encode()).decode()
            }
        secret_metadata = k8s_client.V1ObjectMeta(
            name=credentials_name,
            labels={MY_SECRETS_LABEL_KEY: MY_SECRETS_LABEL_VALUE},
            annotations={"cm_keyonly": "True"},
        )
    elif type == "kubernetes.io/dockerconfigjson":
        registry = form_data.get("registry")
        user = form_data.get("user", "")
        password = form_data.get("password", "")
        auth = str(form_data.get("auth", ""))
        auth_encoded = base64.b64encode(auth.encode()).decode()

        dockercfg_dict = {
            "auths": {
                f"{registry}": {
                    "user": user,
                    "password": password,
                    "auth": auth_encoded,
                }
            }
        }
        dockercfg_json = json.dumps(dockercfg_dict)
        secret_data = {
            ".dockerconfigjson": base64.b64encode(dockercfg_json.encode()).decode()
        }
    else:
        secret_value = [str(sv) for sv in form_data.getlist("secret_value")]
        secret_key = [str(sk).strip() for sk in form_data.getlist("secret_key")]
        data = CredentialsPayload(
            credentials_name=credentials_name,
            secret_value=secret_value,
            secret_key=secret_key,
        )
        secret_data = {
            key: base64.b64encode(value.encode()).decode()
            for key, value in zip(data.secret_key, data.secret_value)
        }

    new_secret = k8s_client.V1Secret(
        metadata=secret_metadata, data=secret_data, type=type
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
        return RedirectResponse(
            url="..",
            status_code=http.HTTPStatus.FOUND,
        )
    else:
        try:
            k8s_client.CoreV1Api().create_namespaced_secret(
                namespace=current_namespace(),
                body=new_secret,
            )
        except ApiException as e:
            raise HTTPException(
                status_code=e.status,
                detail=f"Status {e.status} - {e.reason.title()}: "
                f"{json.loads(e.body).get('message')}",
            )


# This renders the page when you visit the URL
@app.get("/create/", response_class=HTMLResponse)
async def create_form(request: Request):
    return templates.TemplateResponse("create.html", {"request": request})


# This handles the data when the user clicks "Submit"
@app.post("/create/")
async def handle_create(request: Request, ssh_file: UploadFile = File(None)):
    # logic to save data
    form_data = await request.form(max_files=0)
    type = form_data.get("type")
    name = form_data.get("credentials_name")
    create = form_data.get("create")

    if name:
        current_secrets = [s.get("name") for s in get_secret_list()]
        secret_already_exists = name in current_secrets
        if secret_already_exists:
            return templates.TemplateResponse(
                "create.html",
                {
                    "request": request,
                    "secret_already_exists": True,
                    "credentials_name": name,
                    "selected_type": type,
                },
            )

    if create:
        file_content = None
        if type == "kubernetes.io/ssh-auth":
            if ssh_file.filename:
                validated_file = await validate_and_read_key(ssh_file)
                file_content = validated_file.get("content")

        await create_or_update(request, file_content=file_content)

        return RedirectResponse(
            url="..",
            status_code=http.HTTPStatus.FOUND,
        )

    if type == "kubernetes.io/ssh-auth":
        template = "credential_ssh.html"
    elif type == "kubernetes.io/dockerconfigjson":
        template = "credential_dockerconfigjson.html"
    else:
        template = "credential_opaque.html"

    return templates.TemplateResponse(
        template,
        {
            "request": request,
            "secret": {
                "name": name,
                "type": type,
                "data": {},
            },
            "is_new_credential": True,
        },
    )


def update_env_var_annotations(secret, key):
    if isinstance(secret.metadata.annotations, dict):
        secret.metadata.annotations[key] = (
            None if secret.metadata.annotations.get(key) else "True"
        )
    else:
        secret.metadata.annotations = {key: "True"}
    return secret


@app.post("/credentials-detail/{credentials_name}/{app}")
def add_credential_to_app_env(credentials_name: str, app: str):
    secret = ensure_secret_is_mine(credentials_name)
    secret = update_env_var_annotations(secret, f"eoxhub-env-{app}")
    k8s_client.CoreV1Api().patch_namespaced_secret(
        name=credentials_name,
        namespace=current_namespace(),
        body=secret,
    )
    return Response(status_code=http.HTTPStatus.NO_CONTENT)


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
        "annotations": secret.metadata.annotations
        if secret.metadata.annotations
        else {},
        "type": secret.type if secret.type != "Opaque" else "key-value (Opaque)",
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


async def validate_and_read_key(file: UploadFile):
    MAX_FILE_SIZE = 10 * 1024  # 10KB
    ALLOWED_EXTENSIONS = {".pem", ".txt", ""}  # Added empty string for no extension
    KEY_PATTERN = (
        r"-----BEGIN (?P<type>.*?) KEY-----[\s\S]*?-----END (?P=type) KEY-----"
    )

    filename = str(file.filename).lower()
    _, ext = os.path.splitext(filename)

    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported file extension '{ext}'."
        )

    content_bytes = await file.read(MAX_FILE_SIZE + 1)
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 10KB size limit.")

    try:
        text_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="File content is not valid UTF-8 text."
        )

    match = re.search(KEY_PATTERN, text_content)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Security check failed: Valid Key headers (BEGIN/END) not found.",
        )

    return {
        "status": "success",
        "filename": file.filename,
        "key_type": match.group("type"),
        "has_extension": bool(ext),
        "content": text_content,
    }
