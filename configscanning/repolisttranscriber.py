"""
This is a command line tool which transcribes the set of and state of remote repositories
into Repo CRs in a namespace.

That is:
* repo.ai-pipeline.org (Repo) resources are created or deleted so that every relevant repo in GitHub
  as a Repo CR in our namespace and vice versa
* The Repo resources' status fields are updated with up-to-date information about the remote repo.
  In particular, with the last push timestamp.
"""
import argparse
import logging
import sys
from dataclasses import dataclass
from typing import Optional

from kubernetes.dynamic.client import DynamicClient
from kubernetes.dynamic.resource import ResourceInstance

from configscanning import k8sutils
from configscanning.githuborg import AIPIPEGitHubOrganization

logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(
    description="""This transcribes the state of and set of repositories in GitHub into Repo custom
resources in our Kubernetes cluster. This means it will create and delete Repo resources in local
namespace(s) to match the repos visible in GitHub, and will update our record of the last push
date for each one. Synchronization is between a local namespace (usually a Workspace namespace)
and the repos accessible to a GitHub Organization+Team.

There are three modes:
  - With the --all-workspaces flag, this command will locate all AIPIPE Workspaces in Kubernetes
    and synchronize from each Workspace's GitHub Org+Team's repo list into the Workspace's
    namespace.
  - With the --workspace flag, this command will synchronize for only one Workspace in the
    same way.
  - With the --namespace, --organization and --team flags, this command will not look for
    any Workspace objects to determine the source and target, and will instead synchronize as
    specified.
"""
)
parser.add_argument(
    "--app-id-from",
    help="Location of file containing GitHub app ID (note: not 'client id')",
    default="/etc/ai4dte/github-creds/GITHUB_APP_ID",
    type=str,
)
parser.add_argument(
    "--app-private-key-from",
    help="File containing GitHub app private key",
    default="/etc/ai4dte/github-creds/GITHUB_APP_PRIVATE_KEY",
    type=str,
)
parser.add_argument(
    "--all-workspaces",
    help=(
        "This command will transcribe the repos attached to all Workspaces in the cluster into "
        + "their corresponding namespaces."
    ),
    action="store_true",
)
parser.add_argument(
    "--workspace",
    help="This command will transcribe the repos attached to the specified Workspace into its "
    + "corresponding namespace.",
    type=str,
)
parser.add_argument(
    "--namespace",
    help="This command will transcribe into the specified namespace. --organization must also "
    + "be specified.",
    type=str,
)
parser.add_argument(
    "--organization",
    help="This command will transcribe the repos in the specified GitHub Organization (and "
    + "team, if --team is set)",
    type=str,
)
parser.add_argument(
    "--team",
    help="This command will limit the repos transcribed to only those accessible to the "
    + "specified team. Can only be used with --organization and --namespace.",
    type=str,
)


@dataclass
class SourceAndTarget:
    organization: str
    team: Optional[str]
    namespace: str


def tosync_for_all_workspaces():
    """Find all Workspaces in our Kubernetes cluster and create a SourceAndTarget for each."""
    src_targets: list[SourceAndTarget] = []

    with k8sutils.aipipe_resource_dclient("Workspace") as workspaceapi:
        # The type of this is ResourceInstance[WorkspaceList] and it's a list of all Workspaces.
        workspaces = workspaceapi.get()
        for workspace in workspaces["items"]:
            spec = workspace["spec"]
            auth = spec["auth"]
            src_targets.append(
                SourceAndTarget(
                    organization=auth["organization"],
                    team=auth.get("team"),
                    namespace=workspace["status"]["namespaceName"],
                )
            )

    return src_targets


def tosync_for_workspace(name) -> SourceAndTarget:
    """Find the Workspace in our Kubernetes cluster and create a SourceAndTarget."""
    with k8sutils.aipipe_resource_dclient("Workspace") as workspaceapi:
        workspace = workspaceapi.get(name=name)
        spec = workspace["spec"]
        auth = spec["auth"]
        return SourceAndTarget(
            organization=auth["organization"],
            team=auth.get("team"),
            namespace=workspace["status"]["namespaceName"],
        )


def transcribe(app_id, pkey, src_tgt: SourceAndTarget, workspace_name: str = None):
    """Synchronize repo data from the source in GitHub to the target in our Kubernetes cluster"""
    # First, we need the repo data from GitHub.
    ghorg = AIPIPEGitHubOrganization(src_tgt.organization, src_tgt.team)
    ghorg.authenticate_to_github(app_id, pkey)
    gh_repos = {r.name: r for r in ghorg.get_repos()}
    logger.info(
        f"Got repo list from GitHub org/team {src_tgt.organization}:{src_tgt.team}: "
        + f"{gh_repos}"
    )

    # And also the corresponding list of Repos from our cluster.
    with k8sutils.aipipe_resource_dclient("Repo") as repoapi:
        print(f"{type(repoapi)=}, {repoapi=}, {repoapi.delete=}")
        repoapi: DynamicClient

        k8s_repos: dict[str, ResourceInstance] = {}
        # The type of this is ResourceInstance[RepoList] and it's a list of all Workspaces.
        repolist = repoapi.get(namespace=src_tgt.namespace)
        for repo in repolist["items"]:
            # Exclude repos without our label, eg ones not using GitHub.
            src = repo["metadata"].get("annotations", {}).get("ai-pipeline.org/repo-source", "")
            if src.startswith("github:"):
                k8s_repos[repo["metadata"]["name"]] = repo

        logger.info(f"Got repo list from namespace {src_tgt.namespace}: {k8s_repos}")

        # Remove repos gone from GitHub
        repos_removed = k8s_repos.keys() - gh_repos.keys()
        for repo_name in repos_removed:
            logging.info("Removing repo %s from cluster namespace %s", repo_name, src_tgt.namespace)
            repoapi.delete(namespace=src_tgt.namespace, name=repo_name)

        # Add repos added to GitHub
        repos_added = gh_repos.keys() - k8s_repos.keys()
        for repo_name in repos_added:
            repo = gh_repos[repo_name]
            logging.info(f"Adding repo {repo_name} to cluster")
            created_repo = repoapi.create(
                {
                    "apiVersion": "ai-pipeline.org/v1alpha1",
                    "kind": "Repo",
                    "metadata": {
                        "name": repo_name,
                        "namespace": src_tgt.namespace,
                        "annotations": {
                            "ai-pipeline.org/repo-source": f"github:{src_tgt.organization}:{src_tgt.team}",
                        },
                    },
                    "spec": {
                        "workspace": workspace_name,
                        "httpsURL": repo.clone_url,
                        "sshURL": repo.ssh_url,
                        "organization": repo.organization.name if repo.organization else None,
                    },
                }
            )
            logging.info(f"API response to create: {created_repo}")

            repoapi.status.replace(
                {
                    "apiVersion": "ai-pipeline.org/v1alpha1",
                    "kind": "Repo",
                    "metadata": {
                        "name": repo_name,
                        "namespace": src_tgt.namespace,
                        "resourceVersion": created_repo.metadata.resourceVersion,
                    },
                    "status": {
                        "remotePosition": {
                            # Note: repo.pushed_at is only second precision anyway, so this
                            # conversion is not reducing our precision.
                            "lastModified": int(repo.pushed_at.timestamp())
                        },
                    },
                }
            )

        # Update status of existing repos. This means setting status.remotePosition.lastModified
        # in our Repo CR to the pushed_at field from GitHub - but only if it has changed.
        repos_remaining = gh_repos.keys() & k8s_repos.keys()
        for repo_name in repos_remaining:
            gh_repo = gh_repos[repo_name]
            k8s_repo = k8s_repos[repo_name]

            gh_lastmod = int(gh_repo.pushed_at.timestamp())
            k8s_lastmod = k8s_repo.get("status", {}).get("remotePosition", {}).get("lastModified")
            if gh_lastmod != k8s_lastmod:
                logging.info(
                    f"Updating repo {repo_name}, last mod changed to {gh_lastmod} ({gh_repo.pushed_at=})"
                    + f" from {k8s_lastmod}"
                )
                logging.info(
                    f"""Call is repoapi.status.patch(namespace={k8s_repo["metadata"]["namespace"]},
                                                     name={k8s_repo["metadata"]["name"]},
                    body={[
                        {
                            "op": "replace",
                            "path": "/status/remotePosition/lastModified",
                            "value": gh_lastmod,
                        }
                    ]},
                    content_type="application/json-patch+json")'"""
                )
                repoapi.status.patch(
                    namespace=k8s_repo["metadata"]["namespace"],
                    name=k8s_repo["metadata"]["name"],
                    body=[
                        {
                            "op": "replace",
                            "path": "/status/remotePosition/lastModified",
                            "value": gh_lastmod,
                        }
                    ],
                    content_type="application/json-patch+json",
                )


def main():
    """
    This runs when we're invoked as a command-line tool. It's a separate function so that its
    variables have non-global scope.
    """
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    logging.getLogger("configscanning").setLevel(logging.DEBUG)

    args = parser.parse_args()

    #########################################
    # Find the Kubernetes cluster
    k8sutils.init_k8s()

    #########################################
    # Read GitHub credentials.
    app_id, pkey = k8sutils.load_gh_app_creds(args)

    ##########################################
    # Get the list of orgs+teams and namespaces to synchronize
    to_sync: list[SourceAndTarget]

    if args.all_workspaces:
        if args.workspace or args.namespace or args.organization or args.team:
            sys.stderr.write(
                "Cannot use --workspace, --namespace, --organization or --team "
                + "with --all-workspaces.\n"
            )
            sys.exit(1)

        to_sync = tosync_for_all_workspaces()
    elif args.workspace:
        if args.namespace or args.organization or args.team:
            sys.stderr.write("Cannot use --workspace with --namespace, --organization or --team\n")
            sys.exit(1)

        to_sync = [tosync_for_workspace(args.workspace)]
        if to_sync is None:
            sys.stderr.write(f"Workspace {args.workspace} not found.\n")
            sys.exit(2)
    elif args.namespace and args.organization:
        to_sync = [
            SourceAndTarget(
                organization=args.organization, team=args.team, namespace=args.namespace
            )
        ]
    else:
        sys.stderr.write(
            "One of --all-namespaces, --workspace, or --organization and --namespace must be "
            + "specified."
        )
        sys.exit(1)

    ##########################################
    # Synchronize.
    exit_code = 0
    for src_tgt in to_sync:
        try:
            logger.info(
                f"Transcribing repos from {src_tgt.organization}:{src_tgt.team} "
                + f"to ns {src_tgt.namespace}"
            )
            transcribe(app_id, pkey, src_tgt)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(f"Exception transcribing {src_tgt}")
            exit_code = 3

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
