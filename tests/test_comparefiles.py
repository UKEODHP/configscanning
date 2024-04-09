import argparse
import os
import sys
import tempfile
from tempfile import TemporaryDirectory

import boto3
import moto
import pytest

from configscanning.comparefiles import (
    delete_file,
    get_repo_contents,
    get_s3_contents,
    main,
    match_file,
    update_file,
)


@pytest.fixture
def parameters(mock_folder):
    return {
        "name": "my_file.py",
        "folder": f"{mock_folder}/",
        "bucket_name": "test_bucket",
        "s3_folder": "test",
        "exclusions": "",
    }


@pytest.fixture
def test_parser(parameters):
    sys.argv = [parameters["name"]]
    parser = argparse.ArgumentParser()
    parser.add_argument("--clone_dir", default=parameters["folder"], type=str)
    parser.add_argument("--s3_bucket", default=parameters["bucket_name"], type=str)
    parser.add_argument("--s3_folder", default=parameters["s3_folder"], type=str)
    parser.add_argument("--branch", default="main", type=str)
    parser.add_argument("--subdirs_to_ignore", type=str, default="")
    return parser


@pytest.fixture
def mock_folder():
    with TemporaryDirectory() as d:
        yield d


def test_get_repo_contents(parameters, mock_folder):
    test_file_name = "test_file.txt"
    test_file_contents = "file contents\n"
    with open(f"{mock_folder}/{test_file_name}", "w") as f:
        f.write(test_file_contents)

    folder_contents = get_repo_contents(parameters["folder"])
    assert folder_contents == [test_file_name]


def test_get_s3_contents(parameters, mock_folder):
    test_file_name = "test/test_file.txt"

    with moto.mock_aws(), tempfile.NamedTemporaryFile() as temp_file:
        temp_file.write(b"file contents\n")
        temp_file.flush()

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        s3.upload_file(temp_file.name, parameters["bucket_name"], test_file_name)

        s3_resource = boto3.resource("s3")
        files = get_s3_contents(parameters["bucket_name"], s3_resource, "test")

        assert len(files) == 1
        assert files[0].bucket_name == parameters["bucket_name"]
        assert files[0].key == test_file_name


def test_match_file__is_file(parameters):
    with moto.mock_aws(), tempfile.NamedTemporaryFile() as temp_file:
        temp_directory = tempfile.gettempdir()

        test_file_path = temp_file.name
        test_file_name = test_file_path.split("/")[-1]

        temp_file.write(b"file contents\n")
        temp_file.flush()

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])
        s3.upload_file(temp_file.name, parameters["bucket_name"], test_file_name)

        s3_resource = boto3.resource("s3")
        s3_files = s3_resource.Bucket(parameters["bucket_name"]).objects.all()

        file = match_file(test_file_name, s3_files, temp_directory, "")

        assert file.key == test_file_name


def test_match_file__no_file(parameters):
    test_file_name = "test_file.txt"
    with moto.mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        s3_resource = boto3.resource("s3")
        s3_files = s3_resource.Bucket(parameters["bucket_name"]).objects.all()

        file = match_file(test_file_name, s3_files, "/tmp/", "")

        assert file is None


def test_match_file__is_directory(parameters):
    with moto.mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        s3_resource = boto3.resource("s3")
        s3_files = s3_resource.Bucket(parameters["bucket_name"]).objects.all()

        file = match_file("/tmp", s3_files, "/tmp/", "")

        assert file is None


def test_update_file(parameters):
    with moto.mock_aws(), tempfile.NamedTemporaryFile() as temp_file:
        test_file_path = temp_file.name
        test_file_name = test_file_path.split("/")[-1]

        temp_file.write(b"file contents\n")
        temp_file.flush()

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        s3_resource = boto3.resource("s3")
        update_file(test_file_name, "/tmp/", parameters["bucket_name"], s3_resource, "")
        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())

        assert len(s3_files) == 1
        assert s3_files[0].key == test_file_name


def test_delete_file(parameters):
    with moto.mock_aws(), tempfile.NamedTemporaryFile() as temp_file:
        test_file_path = temp_file.name
        test_file_name = test_file_path.split("/")[-1]

        temp_file.write(b"file contents\n")
        temp_file.flush()

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])
        s3.upload_file(temp_file.name, parameters["bucket_name"], test_file_name)

        s3_resource = boto3.resource("s3")
        file_to_delete = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())[0]

        delete_file(file_to_delete)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 0


def test_main__same_file(parameters, test_parser):
    with moto.mock_aws(), tempfile.TemporaryDirectory() as temp_dir:
        sys.argv = [None, temp_dir, parameters["bucket_name"], ""]

        same_file_name = "same.txt"
        folder_path = f"{temp_dir}/test"
        os.makedirs(folder_path)
        path = f"{folder_path}/{same_file_name}"

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        with open(path, "w") as temp_file:
            temp_file.write("file contents\n")
            temp_file.flush()

        s3.upload_file(path, parameters["bucket_name"], f"/test/{same_file_name}")
        s3_resource = boto3.resource("s3")

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1

        main(parser=test_parser)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())

        assert len(s3_files) == 1


def test_main__different_file(parameters, test_parser):
    with moto.mock_aws():
        # sys.argv = [parameters['name'], parameters['folder'], parameters["bucket_name"], ""]

        differences_file_name = "differences.txt"
        folder_path = f"{parameters['folder']}/test"
        os.makedirs(folder_path)
        path = f"{folder_path}/{differences_file_name}"

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        with open(path, "w") as temp_file:
            temp_file.write("file contents\n")
            temp_file.flush()

        s3.upload_file(path, parameters["bucket_name"], f"test/{differences_file_name}")
        s3_resource = boto3.resource("s3")

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1

        with open(path, "w") as temp_file:
            temp_file.write("new contents\n")
            temp_file.flush()

        main(parser=test_parser)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1

        response = s3.get_object(Bucket=parameters["bucket_name"], Key=s3_files[0].key)
        file_content = response.get("Body").read().decode("utf-8")
        assert file_content == "new contents\n"


def test_main__s3_only_file(parameters, test_parser):
    with moto.mock_aws():
        # sys.argv = [parameters['name'], parameters['folder'], parameters["bucket_name"], ""]

        s3_only_file_name = "s3.txt"
        folder_path = f"{parameters['folder']}/test"
        os.makedirs(folder_path)
        path = f"{folder_path}/{s3_only_file_name}"

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        with open(path, "w") as temp_file:
            temp_file.write("file contents\n")
            temp_file.flush()

        s3.upload_file(path, parameters["bucket_name"], f"test/{s3_only_file_name}")
        s3_resource = boto3.resource("s3")

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1

        os.remove(path)

        main(parser=test_parser)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 0


def test_main__local_only_file(parameters, test_parser):
    with moto.mock_aws():
        # sys.argv = [parameters['name'], parameters['folder'], parameters["bucket_name"], ""]

        local_only_file_name = "local.txt"
        folder_path = f"{parameters['folder']}/test"
        os.makedirs(folder_path)
        path = f"{folder_path}/{local_only_file_name}"

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        with open(path, "w") as temp_file:
            temp_file.write("file contents\n")
            temp_file.flush()

        s3_resource = boto3.resource("s3")
        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 0

        main(parser=test_parser)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1


def test_main__s3_excluded_dir(parameters, test_parser):
    with moto.mock_aws():
        sys.argv = [None, "--s3_folder", "different_folder"]

        s3_only_file_name = "s3.txt"
        folder_path = f"{parameters['folder']}/test"
        os.makedirs(folder_path)
        path = f"{folder_path}/{s3_only_file_name}"

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        with open(path, "w") as temp_file:
            temp_file.write("file contents\n")
            temp_file.flush()

        s3.upload_file(path, parameters["bucket_name"], f"test/{s3_only_file_name}")
        s3_resource = boto3.resource("s3")

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1

        os.remove(path)

        main(parser=test_parser)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1


def test_main__s3_excluded_dir_top_level(parameters, test_parser):
    with moto.mock_aws():
        # sys.argv = [parameters['name'], parameters['folder'], parameters["bucket_name"], "subdir"]

        top_level_file_name = "top_level_file.txt"
        folder_path = f"{parameters['folder']}/test"
        os.makedirs(folder_path)
        path = f"{folder_path}/{top_level_file_name}"

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=parameters["bucket_name"])

        with open(path, "w") as temp_file:
            temp_file.write("file contents\n")
            temp_file.flush()

        s3.upload_file(path, parameters["bucket_name"], f"/test/{top_level_file_name}")
        s3_resource = boto3.resource("s3")

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1

        os.remove(path)

        main(parser=test_parser)

        s3_files = list(s3_resource.Bucket(parameters["bucket_name"]).objects.all())
        assert len(s3_files) == 1
