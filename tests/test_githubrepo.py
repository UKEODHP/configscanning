from pathlib import Path

# Pycharm is not looking at dev requirements.
# noinspection PyPackageRequirements
import py.path

# noinspection PyPackageRequirements
import pytest

from configscanning.githubrepo import GitHubRepo

TESTDIR = (Path(__file__).parent / "scratch/configscannertest/").absolute()


def test_determines_repo_name_and_local_location_from_url():
    repo = GitHubRepo(
        location=None,
        parent_dir=str(TESTDIR),
        repourl="https://github.com/AI4DTE/examples-xgboost-simple.git",
    )

    assert repo.gh_org == "AI4DTE"
    assert repo.gh_reponame == "examples-xgboost-simple"
    assert repo.git_host == "github.com"
    assert repo.location == TESTDIR / "github.com/AI4DTE/examples-xgboost-simple"


def test_determines_parent_dir_from_location():
    repo = GitHubRepo(
        location=str(TESTDIR / "github.com/AI4DTE/examples-xgboost-simple"),
        repourl="https://github.com/AI4DTE/examples-xgboost-simple.git",
    )

    assert repo.gh_org == "AI4DTE"
    assert repo.gh_reponame == "examples-xgboost-simple"
    assert repo.git_host == "github.com"
    assert repo.parent_dir == TESTDIR


@pytest.mark.integrationtest
def test_clone_public_repo_with_only_main_branch(tmpdir: py.path.local):
    repo = GitHubRepo(
        location=None,
        parent_dir=str(tmpdir),
        repourl="https://github.com/octocat/Spoon-Knife.git",
    )
    repo.authenticate_to_github(None, None)

    # Checks that it detects that the clone doesn't exist.
    assert repo.repo is None
    assert repo.location == Path(tmpdir / "github.com/octocat/Spoon-Knife")

    repo.update()

    assert repo.repo is not None
    assert (repo.location / ".git" / "refs" / "heads" / "main").exists()
    assert not (repo.location / ".git" / "refs" / "heads" / "develop").exists()
    assert not (repo.location / ".git" / "refs" / "heads" / "test-branch").exists()

    assert repo.ref_positions() == {
        "refs/heads/main": {
            "hash": "d0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9",
            "summary": "Pointing to the guide for forking",
            "commitDate": 1392247244,
        }
    }


@pytest.mark.integrationtest
def test_clone_public_repo_with_nonstandard_branches(tmpdir: py.path.local):
    repo = GitHubRepo(
        location=None,
        parent_dir=str(tmpdir),
        repourl="https://github.com/octocat/Spoon-Knife.git",
        branches_to_fetch={"main", "test-branch"},
    )
    repo.authenticate_to_github(None, None)

    # Checks that it detects that the clone doesn't exist.
    assert repo.repo is None
    assert repo.location == Path(tmpdir / "github.com/octocat/Spoon-Knife")

    repo.update()

    assert set(repo._refspecs_to_pull()) == {
        "refs/heads/main:refs/remotes/origin/main",
        "refs/heads/test-branch:refs/remotes/origin/test-branch",
    }

    assert repo.repo is not None
    assert (repo.location / ".git" / "refs" / "heads" / "main").exists()
    assert not (repo.location / ".git" / "refs" / "heads" / "develop").exists()
    assert (repo.location / ".git" / "refs" / "heads" / "test-branch").exists()

    assert repo.ref_positions() == {
        "refs/heads/main": {
            "hash": "d0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9",
            "summary": "Pointing to the guide for forking",
            "commitDate": 1392247244,
        },
        "refs/heads/test-branch": {
            "hash": "58060701b538587e8b4ab127253e6ed6fbdc53d1",
            "summary": "Create test.md",
            "commitDate": 1399058339,
        },
    }

    # Go back a commit. This is not getting us to exactly the state we'd like to test (the branch
    # remotes/origin/main is in the wrong place), but it's hopefully near enough.
    main_hat_1 = repo.repo.get(repo.repo.branches["main"].target).parents[0]
    repo.repo.branches["main"].set_target(main_hat_1.id)
    repo.repo.head.set_target(main_hat_1.id)

    assert repo.ref_positions() == {
        "refs/heads/main": {
            "hash": "bb4cc8d3b2e14b3af5df699876dd4ff3acd00b7f",
            "summary": "Create styles.css and updated README",
            "commitDate": 1392247135,
        },
        "refs/heads/test-branch": {
            "hash": "58060701b538587e8b4ab127253e6ed6fbdc53d1",
            "summary": "Create test.md",
            "commitDate": 1399058339,
        },
    }

    # Check that another update works.
    repo.update()

    assert repo.ref_positions() == {
        "refs/heads/main": {
            "hash": "d0dd1f61b33d64e29d8bc1372a94ef6a2fee76a9",
            "summary": "Pointing to the guide for forking",
            "commitDate": 1392247244,
        },
        "refs/heads/test-branch": {
            "hash": "58060701b538587e8b4ab127253e6ed6fbdc53d1",
            "summary": "Create test.md",
            "commitDate": 1399058339,
        },
    }


def test_changed_files_between_commits():
    # This is /this/ git repo.
    repo = GitHubRepo(
        location=".",
        repourl="https://github.com/EO-DataHub/configscanning.git",
    )

    file_list = repo.changed_files(
        "e2c95a4233dd25994c02c42010bcbbcd751021cc", "35c92758332eb1f8d0e6be9a5f5ad6960bf051b2"
    )

    assert file_list == {
        "configscanning/comparefiles.py",
        "tests/test_comparefiles.py",
        "pyproject.toml",
        "requirements-dev.txt",
    }


def test_filtered_changed_files_between_commits():
    # This is /this/ git repo.
    repo = GitHubRepo(
        location=".",
        repourl="https://github.com/EO-DataHub/configscanning.git",
    )

    file_list = repo.changed_files(
        "8fe01ff65a5866d85581f9d2c97c0e1682c7c152",
        "eb1b2447b82295f35337f4afaef7fd45be26ec6a",
        only_matching=lambda f: f.endswith(".yaml"),
    )

    assert file_list == {".github/workflows/actions.yaml"}


def test_filtered_all_files_at_commit():
    # This is /this/ git repo.
    repo = GitHubRepo(
        location=".",
        repourl="https://github.com/EO-DataHub/configscanning.git",
    )

    file_list = repo.changed_files(
        since=None,
        until="077f19eaeb22e709b3eca1cc498ea5cd8e1f9add",
        only_matching=lambda f: f.endswith(".yaml"),
    )

    assert file_list == {".github/workflows/docker-image-to-aws-ecr.yaml"}
