from pathlib import Path

import pygit2

# noinspection PyPackageRequirements
import pytest

import configscanning.git_change_scanner
import configscanning.scanners.filelister
from configscanning.githubrepo import GitHubRepo


@pytest.mark.integrationtest
def test_scan_for_yaml(tmpdir):
    repo = GitHubRepo(
        location=None,
        parent_dir=str(tmpdir),
        repourl="https://github.com/octocat/Spoon-Knife.git",
    )

    # Fetch the test repo.
    configscanning.git_change_scanner.pull(None, None, repo)

    # Scan it for files.
    scanned_ptr = configscanning.git_change_scanner.config_scan(
        repo,
        {"main": {configscanning.scanners.filelister.Scanner()}},
        scan_filter=lambda f: True,
    )

    assert set(configscanning.scanners.filelister.visited_files) == {
        Path("README.md"),
        Path("index.html"),
        Path("styles.css"),
    }

    assert scanned_ptr == {
        "refPositions": {
            "refs/heads/main": {
                "hash": "d0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9",
                "summary": "Pointing to the guide for forking",
                "commitDate": 1392247244,
            },
        },
        # "lastModified": 1692350902,   This changes!
        "lastModified": int(repo.get_github_repo().pushed_at.timestamp()),
    }

    # Got c00330d7f1c8f8fd460753a2c946a831b8320a8a
    assert (
        repo.repo.references["refs/tags/_AI4DTE_SCANNED_main"].peel().id
        == "d0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9"
    )

    # Now we test a scan of changes since a particular prior commit.
    repo.checkout_and_reset("refs/heads/main")
    repo.delete_tag("_AI4DTE_SCANNED_main")
    repo.repo.create_tag(
        "_AI4DTE_SCANNED_main",
        repo.repo["a30c19e3f13765a3b48829788bc1cb8b4e95cee4"].id,
        True,
        pygit2.Signature("Name", "email@example.com"),
        "Test tag",
    )
    configscanning.scanners.filelister.visited_files = []
    scanned_ptr = configscanning.git_change_scanner.config_scan(
        repo,
        {"main": {configscanning.scanners.filelister.Scanner()}},
        scan_filter=lambda f: True,
    )

    assert set(configscanning.scanners.filelister.visited_files) == {
        Path("README.md"),
        Path("styles.css"),
    }

    assert (
        repo.repo.references["refs/tags/_AI4DTE_SCANNED_main"].peel().id
        == "d0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9"
    )

    # Finally, we test that scanning with --full-scan ignores the tag and scans everything.
    configscanning.scanners.filelister.visited_files = []
    scanned_ptr = configscanning.git_change_scanner.config_scan(
        repo,
        {"main": {configscanning.scanners.filelister.Scanner()}},
        scan_filter=lambda f: True,
        full_scan=True,
    )

    assert set(configscanning.scanners.filelister.visited_files) == {
        Path("README.md"),
        Path("index.html"),
        Path("styles.css"),
    }
