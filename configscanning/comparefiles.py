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
parser.add_argument("s3_folder", help="S3 subdirectory", type=str)
parser.add_argument("exclusions", help="names of other repos", type=str)


def get_repo_contents(folder: str) -> list:
    """Collects the contents of local repository"""

    return [
        f.replace(folder, "")
        for f in glob.glob(f"{folder}/**", recursive=True)
        if not f.replace(folder, "") == ""
    ]


def get_s3_contents(s3_bucket_name: str, s3: boto3.resource) -> list:
    """Collects the contents of the S3 bucket"""
    bucket = s3.Bucket(s3_bucket_name)

    return list(bucket.objects.all())


def match_file(path: str, s3_contents: list, folder: str, s3_folder: str):
    """Checks to see if file already exists in S3"""
    subdir = f"{s3_folder}/" if s3_folder else ""
    file_path = f"{subdir}{path}"

    if os.path.exists(f"{folder}/{path}") and not os.path.isdir(f"{folder}/{path}"):
        # for f in s3_contents:
        #     print(f.key, path, f.key.startswith(s3_folder))
        return next((f for f in s3_contents if f.key == file_path), None)
    else:
        return None


def update_file(
    path: str, folder: str, s3_bucket_name: str, s3: boto3.resource, s3_folder: str
) -> None:
    """Updates file in S3 from local directory"""
    logging.info(f"Updating {path} into {s3_folder if s3_folder else 'top level'}")

    subdir = f"{s3_folder}/" if s3_folder else ""

    s3.Bucket(s3_bucket_name).upload_file(f"{folder}/{path}", f"{subdir}{path}")


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
    s3_folder = args.s3_folder
    exclusions = args.exclusions.split(",")

    if os.getenv("AWS_ACCESS_KEY") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        session = boto3.session.Session(
            aws_access_key_id=os.environ["AWS_ACCESS_KEY"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )
        s3 = session.resource("s3")

    else:
        s3 = boto3.resource("s3")

    s3_contents = get_s3_contents(s3_bucket, s3)
    repo_contents = get_repo_contents(folder)

    print("XXXXXXXXXXXXXXXXXXXX")
    print(folder)
    print(glob.glob("/tmp"))
    print(repo_contents)

    for path in repo_contents:
        is_outdated = False
        s3_file = match_file(path, s3_contents, folder, s3_folder)

        if s3_file:
            repo_file_contents = open(f"{folder}/{path}").read()
            s3_file_contents = s3_file.get()["Body"].read().decode("utf-8")

            if list(difflib.unified_diff(repo_file_contents, s3_file_contents)):
                is_outdated = True

            s3_contents.remove(s3_file)

        elif not os.path.isdir(
            f"{folder}/{path}"
        ):  # Folders are created automatically when nested files are uploaded to S3
            is_outdated = True

        if is_outdated:
            update_file(path, folder, s3_bucket, s3, s3_folder)

    for file in s3_contents:
        excluded = False
        for exclusion in exclusions:
            if file.key.startswith(f"{exclusion}/") or ("/" not in file.key and s3_folder):

                excluded = True
                break
        if not excluded:
            delete_file(file)


if __name__ == "__main__":
    main()
