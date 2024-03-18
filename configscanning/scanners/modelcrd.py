"""
This scanner finds model config files and creates/updates model.ai-pipeline.org CRs.
"""

import logging

import kubernetes

from configscanning.k8sutils import aipipe_resource_dclient

logger = logging.getLogger(__name__)


class Scanner:
    _namespace: str
    _repourl: str
    _is_prod: bool

    def __init__(
        self,
        namespace="default",
        workspace_namespace="default",
        repourl="",
        is_prod=False,
        **kwargs,
    ):
        self._namespace = namespace
        self._workspace_namespace = workspace_namespace
        self._repourl = repourl
        self._is_prod = is_prod

    def _gen_model_manifest(self, fname, catentry):
        """This converts a model catalogue entry in dictionary form (eg, the output
        of yaml.safe_load) into a Kubernetes model.ai-pipeline.org CR in dictionary form."""
        spec = {
            key: value
            for key, value in catentry.items()
            if key in {"name", "model-serving", "experiment-tracking"}
        }

        # model_serving = spec.setdefault("model-serving", {})

        return {
            "apiVersion": "ai-pipeline.org/v1alpha1",
            "kind": "Model",
            "metadata": {
                "name": catentry["id"],
                "namespace": self._namespace,
                "annotations": {
                    "ai-pipeline.org/config-file-path": str(fname),
                    "ai-pipeline.org/config-file-repo": self._repourl,
                    "ai-pipeline.org/env-type": "exploitation" if self._is_prod else "workspace",
                    "ai-pipeline.org/workspace-namespace": self._workspace_namespace,
                },
            },
            "spec": spec,
        }

    def _submit_manifest_update(self, manifest):
        # TODO: Where we create a Model in the production namespace we should copy the model
        #       artefacts, if necessary, to the production model store. For now we assume that
        #       the production namespace has a secret which can gain access to the workspace
        #       model store (and that the user never modifies/deletes their artefacts).
        with aipipe_resource_dclient("Model") as modelapi:
            try:
                existing_resource = modelapi.get(
                    name=manifest["metadata"]["name"],
                    namespace=manifest["metadata"]["namespace"],
                )

                updated_resource = existing_resource.to_dict()

                if (
                    updated_resource["spec"] != manifest["spec"]
                    or updated_resource["metadata"]["annotations"]
                    != manifest["metadata"]["annotations"]
                ):
                    updated_resource["spec"] = manifest["spec"]
                    updated_resource["metadata"]["annotations"] = manifest["metadata"][
                        "annotations"
                    ]

                    logger.info("Updating Model spec to %s", updated_resource)

                    modelapi.replace(updated_resource)
                else:
                    logging.debug("No need to update model %s", manifest["metadata"]["name"])
            except kubernetes.dynamic.exceptions.NotFoundError:
                logger.info("Creating Model with manifest %s", manifest)
                modelapi.create(manifest)

    def scan_file(self, fname, data):
        if data.get("type") != "model":
            return

        if data.get("platform") != "ai4dte":
            return

        model_manifest = self._gen_model_manifest(fname, data)
        logger.debug("Generated model manifest: %s", model_manifest)

        self._submit_manifest_update(model_manifest)
