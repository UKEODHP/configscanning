"""
This is the command line tool which the workspace controller executes in Kubernetes Jobs in order
to fetch and scan AIPIPE resource configuration files stored in git repositories attached to
Workspaces.
"""

import argparse
import importlib
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import yaml
from github.Repository import Repository

try:
    from yaml import CDumper as Dumper
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import Dumper, SafeLoader

from configscanning import k8sutils
from configscanning.githubrepo import AI4DTERepo


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("repourl", help="repository URL", type=str)
    parser.add_argument(
        "dest", help="checkout location (parent dir of clone)", type=str, default="."
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
        "--enable-scanner",
        help=(
            "Specifies the scanners to run on the repo using Python module names. "
            + "Can be specified multiple times."
        ),
        action="append",
        default=[
            "configscanning.scanners.modelcrd",
        ],
    )
    parser.add_argument(
        "--workspace-namespace",
        help="Target namespace for Kubernetes resources created by the scanner from develop-branch "
        + "catalogue entries",
        type=str,
        default="default",
    )
    parser.add_argument(
        "--prod-namespace",
        help="Target namespace for Kubernetes resources created by the scanner from main-branch "
        + "catalogue entries",
        type=str,
        default="default",
    )
    parser.add_argument(
        "--full-scan",
        help="Scan every file, not just those modified compared to the last scan tag",
        action="store_true",
    )
    parser.add_argument(
        "--pull",
        help="Update (pull or clone) our copy of the repo from upstream",
        action="store_true",
    )
    parser.add_argument(
        "--config-scan",
        help="Scan for and process config files in the cloned repo",
        action="store_true",
    )
    parser.add_argument("--delete", help="Delete the local copy of the repo", action="store_true")
    parser.add_argument("--branch", help="branch to fetch", type=str)

    return parser


def pull(app_id, pkey, clonedrepo):
    """Clones or updates the local repo from its origin"""
    # We take out a lock to prevent concurrent execution of another pull
    # or delete.

    with clonedrepo.lock:
        clonedrepo.authenticate_to_github(app_id, pkey)

        # We check the last pushed date before cloning/pulling because it's a much
        # bigger problem if we miss a change to the upstream repo than if we scan an
        # extra time.
        #
        # We write this to a file so that, when we scan, the config scan can report
        # that it has scanned up to a time measured with the same clock as the push
        # time we record here.
        gh_repo_data: Repository = clonedrepo.get_github_repo()
        pushed_time = int(gh_repo_data.pushed_at.timestamp())
        os.makedirs(Path(clonedrepo.location).parent, exist_ok=True)
        with open(f"{clonedrepo.location}.upstream_push_time", "wt", encoding="ascii") as fobj:
            fobj.write(str(pushed_time))

        # Update / clone repo
        clonedrepo.update()

        # Return updated clone position
        return {
            "refPositions": clonedrepo.ref_positions(),
            "lastModified": pushed_time,
        }


def scannable_file(fname):
    """This returns true if 'fname' is the name of a file the config scanner should scan."""
    return fname.endswith(".yaml") or fname.endswith(".yml") or fname.endswith(".json")


def config_scan(
    clonedrepo: AI4DTERepo,
    branch_scanner_objs: dict[str, set[object]],
    scan_filter=scannable_file,
    full_scan=False,
):
    """Scans and processes the config files in the cloned repo"""
    with clonedrepo.lock:
        with open(f"{clonedrepo.location}.upstream_push_time", "rt", encoding="ascii") as fobj:
            pushed_time = int(fobj.read())

        for branch, scanner_objs in branch_scanner_objs.items():
            # Ignore non-existent branches.
            ref = f"refs/heads/{branch}"
            if not clonedrepo.has_ref(ref):
                continue

            # Need the files available to read.
            clonedrepo.checkout_and_reset(ref)

            # Find files changed since last scan.
            last_scan_tag = f"_AI4DTE_SCANNED_{branch}"
            last_scan_tag_ref = f"refs/tags/{last_scan_tag}"
            files_to_scan = clonedrepo.changed_files(
                (
                    last_scan_tag
                    if not full_scan and clonedrepo.has_ref(last_scan_tag_ref)
                    else None
                ),
                only_matching=scan_filter,
            )

            # Scan the files.
            for fname in files_to_scan:
                with open(clonedrepo.location / fname, "rt", encoding="utf8") as file:
                    if fname.endswith(".yaml") or fname.endswith(".yml"):
                        data = yaml.load(file, SafeLoader)
                    elif fname.endswith(".json"):
                        data = json.load(file)
                    else:
                        data = file.read()

                logging.debug("Scanning file %s", fname)
                for scanner_obj in scanner_objs:
                    scanner_obj.scan_file(Path(fname), data)

            # Tag the last scan position so we can find it next time.
            clonedrepo.create_tag(last_scan_tag, "Config scanner ran to here")

        # Print updated repo state.
        return {
            "refPositions": clonedrepo.ref_positions(),
            "lastModified": pushed_time,
        }


def main(parser=None):
    """
    This runs when we're invoked as a command-line tool. It's a separate function so that its
    variables have non-global scope.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("configscanning").setLevel(logging.DEBUG)

    if parser is None:
        parser = get_parser()
    args, _ = parser.parse_known_args()

    k8sutils.init_k8s()

    # This will be printed at the end and is the JSON patch required to update the
    # Repo CR's status.
    patch = {"status": {}}

    # Locate repo / repo destination.
    clonedrepo = AI4DTERepo(
        location=None,
        parent_dir=args.dest,
        repourl=args.repourl,
        branches_to_fetch={args.branch},
    )

    if args.pull:
        # Update or clone the repo from its origin.
        # Gather GitHub credentials.
        app_id, pkey = k8sutils.load_gh_app_creds(args)
        patch["status"]["clonePosition"] = pull(app_id, pkey, clonedrepo)

    if args.config_scan:
        # Scan the repo branches for config files and process them.
        scanner_mods = {importlib.import_module(modname) for modname in args.enable_scanner}

        def create_scanner_objs(namespace, is_prod):
            return list(
                map(
                    lambda mod: mod.Scanner(
                        namespace=namespace,
                        repourl=args.repourl,
                        is_prod=is_prod,
                        workspace_namespace=args.workspace_namespace,
                    ),
                    scanner_mods,
                )
            )

        patch["status"]["configScanPosition"] = config_scan(
            clonedrepo,
            {
                "main": create_scanner_objs(args.prod_namespace, True),
                "develop": create_scanner_objs(args.workspace_namespace, False),
            },
            full_scan=args.full_scan,
        )

    if args.delete:
        with clonedrepo.lock:
            # Delete our clone from disk.
            if os.access(clonedrepo.location, 0):
                shutil.rmtree(clonedrepo.location)

        patch["status"]["clonePosition"] = None

    # Print update to Repo CR's status field.
    sys.stderr.write(f"Patch is {patch}\n")
    print(yaml.dump(patch, Dumper=Dumper, default_flow_style=False))

    # "python3",
    # "-m",
    # "configscanning.comparefiles",
    # "/tmp/element84-data/github.com/UKEODHP/element84-data/",
    # "catalogue-data",
    # "catalogue-data/element84-data",


if __name__ == "__main__":
    main()
