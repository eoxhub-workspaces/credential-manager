from contextlib import contextmanager
from unittest import mock

from kubernetes import client as k8s_client
import pytest

from my_credentials.views import B64DecodedAccessDict


@contextmanager
def do_mock_secret_list(secrets):
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.list_namespaced_secret",
        return_value=k8s_client.V1SecretList(items=secrets),
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
