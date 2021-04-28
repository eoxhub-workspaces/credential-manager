from unittest import mock

from kubernetes import client as k8s_client
import pytest

from my_credentials.views import B64DecodedAccessDict


@pytest.fixture()
def mock_secret_list_empty():
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.list_namespaced_secret",
        return_value=k8s_client.V1SecretList(items=[]),
    ) as mocker:
        yield mocker


@pytest.fixture()
def mock_secret_list_one_secret(secret):
    with mock.patch(
        "my_credentials.views.k8s_client.CoreV1Api.list_namespaced_secret",
        return_value=k8s_client.V1SecretList(items=[secret]),
    ) as mocker:
        yield mocker


@pytest.mark.asyncio
async def test_credentials_show_no_results_initially(client, mock_secret_list_empty):
    response = await client.get("/")
    assert "no credentials" in response.text


@pytest.mark.asyncio
async def test_credentials_are_shown(
    client,
    mock_secret_list_one_secret,
    secret,
):
    response = await client.get("/")

    assert "username" in response.text
    assert B64DecodedAccessDict(secret.data)["username"] in response.text


@pytest.mark.skip
@pytest.mark.asyncio
async def test_only_labelled_credentials_are_shown(client):
    raise NotImplementedError
