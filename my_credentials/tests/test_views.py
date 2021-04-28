import base64
from contextlib import contextmanager
from unittest import mock

from kubernetes import client as k8s_client
import pytest

from my_credentials.views import B64DecodedAccessDict


@contextmanager
def do_mock_secret_list(secrets: list[k8s_client.V1Secret]):
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.list_namespaced_secret",
        return_value=k8s_client.V1SecretList(items=secrets),
    ) as mocker:
        yield mocker


@contextmanager
def do_mock_secret_read(secret: k8s_client.V1Secret):
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.read_namespaced_secret",
        return_value=secret,
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_secret_create():
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.create_namespaced_secret",
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_secret_patch():
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.patch_namespaced_secret",
    ) as mocker:
        yield mocker


@pytest.mark.asyncio
async def test_credentials_show_no_results_initially(client):
    with do_mock_secret_list(secrets=[]):
        response = await client.get("/")
    assert "no credentials" in response.text


@pytest.mark.asyncio
async def test_credentials_are_shown(
    client,
    secret,
):
    with do_mock_secret_list(secrets=[secret]):
        response = await client.get("/")

    assert "username" in response.text
    assert B64DecodedAccessDict(secret.data)["username"] in response.text


@pytest.mark.asyncio
async def test_only_labelled_credentials_are_shown(client, secret):
    with do_mock_secret_list(secrets=[]) as mocker:
        await client.get("/")

    assert "my-credentials" in mocker.mock_calls[0].kwargs["label_selector"]


@pytest.mark.asyncio
async def test_edit_credentials_shows_contents(client, secret):
    with do_mock_secret_read(secret):
        response = await client.get(f"/credentials-detail/{secret.metadata.name}")

    assert "username" in response.text
    assert B64DecodedAccessDict(secret.data)["username"] in response.text


def create_form_data(is_update: bool):
    return "&".join(
        [
            f"{k}={v}"
            for k, v in [
                ("secret_key", "user"),
                ("secret_key", "pw"),
                ("secret_value", "testington"),
                ("secret_value", "supersecret"),
            ]
            + ([] if is_update else [("credentials_name", "new-secret")])
        ]
    )


@pytest.mark.asyncio
async def test_edit_credentials_updates_secrets(client, mock_secret_patch):
    response = await client.post(
        "/credentials-detail/existing-secret",
        # NOTE: can't just pass form because async_asgi_testclient doesn't support
        #       multidicts
        data=create_form_data(is_update=True),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=False,
    )

    kwargs = mock_secret_patch.mock_calls[0].kwargs
    assert (
        kwargs["body"].data["user"] == base64.b64encode("testington".encode()).decode()
    )
    assert kwargs["body"].metadata.name == "existing-secret"

    assert response.headers["location"] == "/"


@pytest.mark.asyncio
async def test_create_credentials_creates_secrets(client, mock_secret_create):
    response = await client.post(
        "/credentials-detail/",
        # NOTE: can't just pass form because async_asgi_testclient doesn't support
        #       multidicts
        data=create_form_data(is_update=False),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=False,
    )

    kwargs = mock_secret_create.mock_calls[0].kwargs
    assert (
        kwargs["body"].data["user"] == base64.b64encode("testington".encode()).decode()
    )
    assert kwargs["body"].metadata.name == "new-secret"

    assert response.headers["location"] == "/"
