import argparse
import difflib
import glob
import logging
import os
from typing import Optional

import boto3

from configscanning import k8sutils

logger = logging.getLogger(__name__)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clone_dir", help="local directory of cloned repo", type=str)
    parser.add_argument("--s3_bucket", help="S3 bucket", type=str)
    parser.add_argument("--s3_folder", help="S3 subdirectory", type=str)
    parser.add_argument("--branch", help="branch to fetch", type=str)
    parser.add_argument(
        "--subdirs_to_ignore", help="subdirectories to ignore", type=str, default=""
    )
    return parser


def get_repo_contents(folder: str) -> list:
    """Collects the contents of local repository"""

    return [
        f.replace(folder, "")
        for f in glob.glob(f"{folder}/**", recursive=True)
        if f.endswith(".json") and not f.replace(folder, "") == ""
    ]


def get_s3_contents(s3_bucket_name: str, s3: boto3.resource, s3_folder: str) -> list:
    """Collects the contents of the S3 bucket"""
    logging.info(f"Collecting contents of {s3_bucket_name}")
    bucket = s3.Bucket(s3_bucket_name)

    files_in_s3 = list(bucket.objects.filter(Prefix=s3_folder).all())
    folder_contents = [f for f in files_in_s3 if f.key.startswith(f"{s3_folder}/")]

    if s3_folder.count("/") == 0:  # i.e. top level only
        folder_contents = [f for f in folder_contents if f.key.count("/") == 1]

    return folder_contents


def match_file(path: str, s3_contents: list, folder: str, s3_folder: str, subdirs_to_ignore=None):
    """Checks to see if file already exists in S3"""
    subdir = f"{s3_folder}" if s3_folder else ""
    file_path = f"{subdir}/{path}"
    path = path.rstrip("/")

    if os.path.exists(f"{folder}{subdirs_to_ignore}{path}") and not os.path.isdir(
        f"{folder}{subdirs_to_ignore}{path}"
    ):
        return next((f for f in s3_contents if f.key == file_path), None)
    else:
        return None


def update_file(
    path: str,
    folder: str,
    s3_bucket_name: str,
    s3: boto3.resource,
    s3_folder: str,
    subdirs_to_ignore: Optional[str] = "",
) -> str:
    """Updates file in S3 from local directory"""
    logging.info(f"Updating {path} into {s3_folder if s3_folder else 'top level'}")

    subdir = f"{s3_folder}" if s3_folder else ""
    path = path.rstrip("/")
    s3.Bucket(s3_bucket_name).upload_file(f"{folder}{subdirs_to_ignore}{path}", f"{subdir}/{path}")
    return f"{subdir}/{path}"


def delete_file(s3_file) -> None:
    """Deletes any files no longer present"""
    logging.info(f"Deleting {s3_file}")

    s3_file.delete()


def main(parser=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("configscanning").setLevel(logging.DEBUG)

    if parser is None:
        parser = get_parser()

    args, _ = parser.parse_known_args()
    k8sutils.init_k8s()

    folder = os.path.join(args.clone_dir, "")
    s3_bucket = args.s3_bucket
    s3_folder = args.s3_folder
    subdirs_to_ignore = args.subdirs_to_ignore + "/" if args.subdirs_to_ignore else "/"

    added_files = []
    updated_files = []
    deleted_files = []

    if os.getenv("AWS_ACCESS_KEY") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        session = boto3.session.Session(
            aws_access_key_id=os.environ["AWS_ACCESS_KEY"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        s3 = session.resource("s3")

    else:
        s3 = boto3.resource("s3")

    s3_contents = get_s3_contents(s3_bucket, s3, s3_folder)
    repo_contents = get_repo_contents(os.path.join(folder, subdirs_to_ignore))

    for path in repo_contents:
        is_outdated = False
        s3_file = match_file(
            path, s3_contents, folder, s3_folder, subdirs_to_ignore=subdirs_to_ignore
        )

        is_new = False

        if s3_file:
            repo_file_contents = open(f"{folder}{subdirs_to_ignore}{path}").read()
            s3_file_contents = s3_file.get()["Body"].read().decode("utf-8")

            if list(difflib.unified_diff(repo_file_contents, s3_file_contents)):
                is_outdated = True

            s3_contents.remove(s3_file)

        elif not os.path.isdir(
            f"{folder}{subdirs_to_ignore}{path}"
        ):  # Folders are created automatically when nested files are uploaded to S3
            is_outdated = True
            is_new = True

        if is_outdated:
            file = update_file(
                path, folder, s3_bucket, s3, s3_folder, subdirs_to_ignore=subdirs_to_ignore
            )
            if is_new:
                added_files.append(file)
            else:
                updated_files.append(file)

    for file in s3_contents:
        delete_file(file)
        deleted_files.append(file.key)

    return {
        "bucket_name": s3_bucket,
        "added_keys": added_files,
        "updated_keys": updated_files,
        "deleted_keys": deleted_files,
    }


if __name__ == "__main__":
    main()
