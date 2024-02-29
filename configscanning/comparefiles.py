import argparse
import difflib
import glob
import logging
import os

import boto3

from configscanning import k8sutils

parser = argparse.ArgumentParser()
parser.add_argument("clone_dir", help="local directory of cloned repo", type=str)
parser.add_argument("s3_bucket", help="S3 bucket", type=str)


def get_repo_contents(folder: str) -> list:
    """Collects the contents of local repository"""

    return [
        f.replace(folder, "")
        for f in glob.glob(f"{folder}/**", recursive=True)
        if not f.replace(folder, "") == ""
    ]


def get_s3_contents(s3_bucket_name: str) -> list:
    """Collects the contents of the S3 bucket"""
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(s3_bucket_name)

    return list(bucket.objects.all())


def match_file(path: str, s3_contents: list, folder: str):
    """Checks to see if file already exists in S3"""

    if os.path.exists(f"{folder}/{path}") and not os.path.isdir(f"{folder}/{path}"):
        return next((f for f in s3_contents if f.key == path), None)
    else:
        return None


def update_file(path: str, folder: str, s3_bucket_name: str) -> None:
    """Updates file in S3 from local directory"""
    logging.info(f"Updating {path}")
    s3 = boto3.resource("s3")

    s3.Bucket(s3_bucket_name).upload_file(f"{folder}/{path}", path)


def delete_file(s3_file) -> None:
    """Deletes any files no longer present"""
    logging.info(f"Deleting {s3_file}")

    s3_file.delete()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("configscanning").setLevel(logging.DEBUG)

    args = parser.parse_args()
    k8sutils.init_k8s()

    folder = args.clone_dir
    s3_bucket = args.s3_bucket

    s3_contents = get_s3_contents(s3_bucket)
    repo_contents = get_repo_contents(folder)

    updated_files = []

    for path in repo_contents:
        is_outdated = False
        s3_file = match_file(path, s3_contents, folder)

        if s3_file:
            repo_file_contents = open(f"{folder}/{path}").read()
            s3_file_contents = s3_file.get()["Body"].read().decode("utf-8")

            if list(difflib.unified_diff(repo_file_contents, s3_file_contents)):
                updated_files.append(path)
                is_outdated = True

            s3_contents.remove(s3_file)

        elif not os.path.isdir(
                f"{folder}/{path}"
        ):  # Folders are created automatically when nested files are uploaded to S3
            is_outdated = True

        if is_outdated:
            update_file(path, folder, s3_bucket)

    for file in s3_contents:
        delete_file(file)


if __name__ == "__main__":
    main()
