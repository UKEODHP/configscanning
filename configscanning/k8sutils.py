"""Utilities for interactive with Kubernetes (plus a bit of scope creep)"""

import os
from contextlib import contextmanager

import kubernetes
from kubernetes.client import CoreV1Api, V1ConfigMap


def init_k8s():
    """Load our Kubernetes config. Call this before using Kubernetes."""
    if "KUBERNETES_SERVICE_HOST" in os.environ:
        kubernetes.config.load_incluster_config()
    else:
        kubernetes.config.load_kube_config()


def get_ai4dte_config():
    """Returns the AI4DTE config configmap"""
    with kubernetes.client.ApiClient() as k8s_client:
        ai4dte_config: V1ConfigMap = CoreV1Api(k8s_client).read_namespaced_config_map(
            "ai4dte-config", "ai4dte"
        )

        return ai4dte_config


# class AIPIPEDClient:
#     def __init__(self, kind) -> None:
#         self.kind = kind

#     def __enter__(self):


# def with_aipipe_resource_dclient(kind, fn):
#     with kubernetes.client.ApiClient() as k8s_client:
#         dclient = kubernetes.dynamic.DynamicClient(k8s_client)
#         api = dclient.resources.get(api_version="ai-pipeline.org/v1alpha1", kind=kind)
#         return fn(api)


@contextmanager
def aipipe_resource_dclient(kind, api_version="ai-pipeline.org/v1alpha1"):
    """This returns a context-managed k8s Dynamic Client for the specified CRD"""
    with kubernetes.client.ApiClient() as k8s_client:
        dclient = kubernetes.dynamic.DynamicClient(k8s_client)
        api = dclient.resources.get(api_version=api_version, kind=kind)
        yield api


def load_gh_app_creds(args):
    """Given our command line args, this loads the GitHub credentials specified"""
    if os.access(args.app_id_from, 0):
        with open(args.app_id_from, "rt", encoding="ascii") as file:
            app_id = int(file.read())
    else:
        app_id = os.getenv("GITHUB_APP_ID")

    if os.access(args.app_private_key_from, 0):
        with open(args.app_private_key_from, "rt", encoding="ascii") as file:
            pkey = file.read()
    else:
        pkey = os.getenv("GITHUB_APP_PRIVATE_KEY")

    return app_id, pkey
