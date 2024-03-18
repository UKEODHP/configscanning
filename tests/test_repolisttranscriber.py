import logging
from datetime import datetime
from unittest import mock
from unittest.mock import Mock

from pytest_mock import MockerFixture

import configscanning.repolisttranscriber
from configscanning.repolisttranscriber import SourceAndTarget, transcribe

# noinspection PyPackageRequirements


# This can be useful for experimentation with the real API in the JASMIN dev cluster.
# Probably not such a good routine unit test, though.
#
# @pytest.mark.integrationtest
# def test_get_repos_for_team_returns_correct_repos():
#     if "KUBERNETES_SERVICE_HOST" in os.environ:
#         kubernetes.config.load_incluster_config()
#     else:
#         kubernetes.config.load_kube_config(context="oidc@dev-kubernetes")

#     with kubernetes.client.ApiClient() as k8s_client:
#         ai4dteConfig: V1ConfigMap = CoreV1Api(k8s_client).read_namespaced_config_map(
#             "ai4dte-config", "ai4dte"
#         )

#     all_workspaces = configscanning.repolisttranscriber.tosync_for_all_workspaces()

#     assert all_workspaces == {}


def test_get_all_sync_targets_returns_correct_targets(mocker: MockerFixture):
    mocker.patch("kubernetes.config")
    mocker.patch("kubernetes.client")
    dyn_mock = mocker.patch("kubernetes.dynamic.DynamicClient")

    test_k8s_returned_list = {
        "items": [
            {
                "spec": {"auth": {"organization": "org1", "team": "team1"}},
                "status": {"namespaceName": "ns1"},
            },
            {"spec": {"auth": {"organization": "org2"}}, "status": {"namespaceName": "ns2"}},
        ]
    }

    wsapi = dyn_mock().resources.get(api_version=mock.ANY, kind="Workspace")
    wsapi.get.return_value = test_k8s_returned_list

    all_workspaces = configscanning.repolisttranscriber.tosync_for_all_workspaces()

    assert all_workspaces == [
        configscanning.repolisttranscriber.SourceAndTarget(
            organization="org1", team="team1", namespace="ns1"
        ),
        configscanning.repolisttranscriber.SourceAndTarget(
            organization="org2", team=None, namespace="ns2"
        ),
    ]


def test_get_sync_targets_for_workspace_returns_correct_targets(mocker: MockerFixture):
    mocker.patch("kubernetes.config")
    mocker.patch("kubernetes.client")
    dyn_mock = mocker.patch("kubernetes.dynamic.DynamicClient")

    test_k8s_returned_ws = {
        "spec": {"auth": {"organization": "org1", "team": "team1"}},
        "status": {"namespaceName": "ns1"},
    }

    wsapi = dyn_mock().resources.get(api_version=mock.ANY, kind="Workspace")
    wsapi.get.return_value = test_k8s_returned_ws

    ws = configscanning.repolisttranscriber.tosync_for_workspace("ws1")

    assert ws == configscanning.repolisttranscriber.SourceAndTarget(
        organization="org1", team="team1", namespace="ns1"
    )


def test_transcribe_no_targets_does_nothing(mocker: MockerFixture):
    mocker.patch("kubernetes.config")
    mocker.patch("kubernetes.client")
    ghorg_mock = mocker.patch("configscanning.repolisttranscriber.AIPIPEGitHubOrganization")
    dyn_mock = mocker.patch("kubernetes.dynamic.DynamicClient")

    # Simulate no repos in GH, no repos in k8s.
    ghorg_mock.get_repos.return_value = []
    repoapi = dyn_mock().resources.get(api_version=mock.ANY, kind="Repo")
    repoapi.get.return_value = {"items": []}

    transcribe(123, "", SourceAndTarget(organization="org", team="team", namespace="tgtns"))

    repoapi.get.assert_called_once_with(namespace="tgtns")
    repoapi.delete.assert_not_called()
    repoapi.patch.assert_not_called()
    repoapi.create.assert_not_called()


def test_transcribe_synchronizes_difference(mocker: MockerFixture, caplog):
    caplog.set_level(logging.DEBUG)
    mocker.patch("kubernetes.config")
    mocker.patch("kubernetes.client")
    ghorg_mock = mocker.patch("configscanning.repolisttranscriber.AIPIPEGitHubOrganization")
    dyn_mock = mocker.patch("kubernetes.dynamic.DynamicClient")

    # Simulate repos A, B and C in GH, B and C in in K8S with C changed, D in k8S.
    gh_mocks = [Mock(), Mock(), Mock()]
    gh_mocks[0].name = "A"
    gh_mocks[0].pushed_at = datetime.fromtimestamp(123456)
    gh_mocks[0].clone_url = "https://example.com/org/A"
    gh_mocks[0].ssh_url = "git@example.com:org/A"
    gh_mocks[0].organization.name = "org"

    gh_mocks[1].name = "B"
    gh_mocks[1].pushed_at = datetime.fromtimestamp(234567)

    gh_mocks[2].name = "C"
    gh_mocks[2].pushed_at = datetime.fromtimestamp(345678)

    ghorg_mock().get_repos.return_value = gh_mocks

    repoapi = dyn_mock().resources.get(api_version=mock.ANY, kind="Repo")
    repoapi.get.return_value = {
        "items": [
            {
                "metadata": {
                    "name": "B",
                    "namespace": "tgtns",
                    "annotations": {"ai-pipeline.org/repo-source": "github:org:team"},
                },
                "status": {"remotePosition": {"lastModified": 234567}},
            },
            {
                "metadata": {
                    "name": "C",
                    "namespace": "tgtns",
                    "annotations": {"ai-pipeline.org/repo-source": "github:org:team"},
                },
                "status": {"remotePosition": {"lastModified": 345677}},
            },
            {
                "metadata": {
                    "name": "D",
                    "namespace": "tgtns",
                    "annotations": {"ai-pipeline.org/repo-source": "github:org:team"},
                },
                "status": {"remotePosition": {"lastModified": 456789}},
            },
            {
                "metadata": {
                    "name": "E",
                    "namespace": "tgtns",
                },
                "status": {"remotePosition": {"lastModified": 456789}},
            },
        ]
    }
    cmock = Mock()
    cmock.metadata.resourceVersion = 123
    repoapi.create.return_value = cmock

    transcribe(123, "", SourceAndTarget(organization="org", team="team", namespace="tgtns"), "ws")

    repoapi.get.assert_called_once_with(namespace="tgtns")
    repoapi.delete.assert_called_once_with(namespace="tgtns", name="D")
    repoapi.status.patch.assert_called_once_with(
        body=[{"op": "replace", "path": "/status/remotePosition/lastModified", "value": 345678}],
        name="C",
        namespace="tgtns",
        content_type="application/json-patch+json",
    )
    repoapi.create.assert_called_once_with(
        {
            "apiVersion": "ai-pipeline.org/v1alpha1",
            "kind": "Repo",
            "metadata": {
                "name": "A",
                "namespace": "tgtns",
                "annotations": {
                    "ai-pipeline.org/repo-source": "github:org:team",
                },
            },
            "spec": {
                "workspace": "ws",
                "httpsURL": "https://example.com/org/A",
                "sshURL": "git@example.com:org/A",
                "organization": "org",
            },
        }
    )
    repoapi.status.replace.assert_called_once_with(
        {
            "apiVersion": "ai-pipeline.org/v1alpha1",
            "kind": "Repo",
            "metadata": {
                "name": "A",
                "namespace": "tgtns",
                "resourceVersion": 123,
            },
            "status": {
                "remotePosition": {
                    "lastModified": 123456,
                },
            },
        }
    )
