from copy import deepcopy
from unittest import mock

# noinspection PyPackageRequirements
import kubernetes
import kubernetes.dynamic.exceptions
import yaml

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader

from pytest_mock import MockerFixture

from configscanning.scanners.modelcrd import Scanner

TEST_MODEL_MLFLOW = """type: Model
name: Test model
id: test-model-mlflow
model-serving:
  model-server: mlflow

  artifacts:
    source: mlflow
    url: https://mlflow.workspace-sample.workspaces.ai4dte.eco-ke-staging.com/

  expose:
    1.0.0: a9469e982d254c56bb4df5d95b306e26
    1.0.1: test4/sincere-sloth-95

experiment-tracking:
  type: workspace-mlflow
  url: https://mlflow.workspace-sample.workspaces.ai4dte.eco-ke-staging.com/
"""


def _set_up_scanner_with_test_manifest(mocker: MockerFixture):
    mocker.patch("kubernetes.config")
    mocker.patch("kubernetes.client")
    dyn_mock = mocker.patch("kubernetes.dynamic.DynamicClient")

    scanner = Scanner(namespace="ns", repourl="https://example.com/org/repo.git")
    manifest = scanner._gen_model_manifest(
        "tests/test-file.yaml",
        yaml.load(TEST_MODEL_MLFLOW, SafeLoader),
    )

    modelapi = dyn_mock().resources.get(api_version=mock.ANY, kind="Model")

    return dyn_mock, scanner, manifest, modelapi


def test_gen_manifest(mocker: MockerFixture):
    _, _, manifest, _ = _set_up_scanner_with_test_manifest(mocker)

    assert manifest == {
        "apiVersion": "ai-pipeline.org/v1alpha1",
        "kind": "Model",
        "metadata": {
            "name": "test-model-mlflow",
            "namespace": "ns",
            "annotations": {
                "ai-pipeline.org/config-file-path": "tests/test-file.yaml",
                "ai-pipeline.org/config-file-repo": "https://example.com/org/repo.git",
                "ai-pipeline.org/env-type": "workspace",
                "ai-pipeline.org/workspace-namespace": "default",
            },
        },
        "spec": {
            "name": "Test model",
            "model-serving": {
                "model-server": "mlflow",
                "artifacts": {
                    "source": "mlflow",
                    "url": "https://mlflow.workspace-sample.workspaces.ai4dte.eco-ke-staging.com/",
                },
                "expose": {
                    "1.0.0": "a9469e982d254c56bb4df5d95b306e26",
                    "1.0.1": "test4/sincere-sloth-95",
                },
            },
            "experiment-tracking": {
                "type": "workspace-mlflow",
                "url": "https://mlflow.workspace-sample.workspaces.ai4dte.eco-ke-staging.com/",
            },
        },
    }


def test_manifest_created_if_not_exists(mocker: MockerFixture):
    dyn_mock, scanner, manifest, modelapi = _set_up_scanner_with_test_manifest(mocker)

    modelapi.get.side_effect = kubernetes.dynamic.exceptions.NotFoundError(mock.Mock())

    scanner._submit_manifest_update(manifest)

    modelapi.get.assert_called_once()
    modelapi.create.assert_called_once_with(manifest)


def test_manifest_updated_if_changed(mocker: MockerFixture):
    dyn_mock, scanner, manifest, modelapi = _set_up_scanner_with_test_manifest(mocker)

    existing = deepcopy(manifest)
    existing["spec"]["name"] = "Wrong name"
    existing["metadata"]["test"] = "Test"
    modelapi.get().to_dict.return_value = existing

    scanner._submit_manifest_update(manifest)

    expect = deepcopy(existing)
    expect["spec"]["name"] = manifest["spec"]["name"]
    modelapi.replace.assert_called_once_with(expect)
    modelapi.create.assert_not_called()


def test_manifest_updated_if_annotation_changed(mocker: MockerFixture):
    dyn_mock, scanner, manifest, modelapi = _set_up_scanner_with_test_manifest(mocker)

    existing = deepcopy(manifest)
    modelapi.get().to_dict.return_value = existing

    manifest["metadata"]["annotations"]["test-annotation"] = "New annotation"
    scanner._submit_manifest_update(manifest)

    expect = deepcopy(existing)
    expect["metadata"]["annotations"]["test-annotation"] = "New annotation"
    modelapi.replace.assert_called_once_with(expect)
    modelapi.create.assert_not_called()


def test_manifest_not_updated_if_not_changed(mocker: MockerFixture):
    dyn_mock, scanner, manifest, modelapi = _set_up_scanner_with_test_manifest(mocker)

    modelapi.get().to_dict.return_value = deepcopy(manifest)

    scanner._submit_manifest_update(manifest)

    modelapi.replace.assert_not_called()
    modelapi.create.assert_not_called()
