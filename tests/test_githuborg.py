# noinspection PyPackageRequirements
import pytest

from configscanning.githuborg import AIPIPEGitHubOrganization


@pytest.mark.integrationtest
def test_get_repos_for_team_returns_correct_repos():
    ghorg = AIPIPEGitHubOrganization("AI4DTE", "unit-test-team-1")
    # ghorg = AIPIPEGitHubOrganization("AI4DTE", None)

    # Add a file called this with a private key generated at the bottom of
    # https://github.com/organizations/AI4DTE/settings/apps/ai4dte-kind-dev-ahayward
    with open("scratch/ai4dte-kind-dev-ahayward-private-key", "rt") as file:
        pkey = file.read()

    ghorg.authenticate_to_github(367601, pkey)

    repos = ghorg.get_repos()
    assert {repo.name for repo in repos} == {"test-models"}
