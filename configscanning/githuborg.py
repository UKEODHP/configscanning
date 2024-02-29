"""Tools for use with GitHub Organizations"""
from typing import Iterable, Optional

from github import Auth, GithubIntegration
from github.Installation import Installation
from github.Repository import Repository


class AIPIPEGitHubOrganization:
    """This represents a GitHub Organization which we believe is linked to an AIPIPE Workspace"""

    orgname: str
    teamname: str
    # _github: [Github | None]
    _gh_installation: Optional[Installation]

    def __init__(
        self,
        orgname: str,
        teamname: str | None,
    ):
        """
        This represents a GitHub Organization and, optionally, Team, usually one we believe is
        linked to our Workspace(s).
        """
        self.orgname = orgname
        self.teamname = teamname

        # self._github = None
        self._gh_installation = None
        self._access_token = None

    def authenticate_to_github(self, app_id: int, app_private_key: str):
        """
        Authenticate to GitHub as an app installation.

        Args:
              app_id (str): AIPIPE GitHub App ID - provided when we register our app.
                            There is one per app registration (this is not app installation
                            specific, but rather AIPIPE installation specific).
              app_private_key (str): A private generated for our app registration in the app
                                     management page github.com/organizations/AI4DTE/settings/apps
        """
        # First we must authenticate as the app, which gives us limited access.
        auth = Auth.AppAuth(app_id, app_private_key)
        ghi = GithubIntegration(auth=auth)

        # We can use this to find the app installation for the organization, then get an
        # authenticated client object from there.
        self._gh_installation: Installation = ghi.get_org_installation(self.orgname)

        # Now we can get a full client object which can use the full Organization APIs.
        # self._github = gh_installation.get_github_for_installation()

        # return self._github

    def get_repos(self) -> Iterable[Repository]:
        """
        Returns a list of the repositories we can pull in this Organization and, if a team was
        specified, are accessible to the Team. This may exclude some repos if the Organization
        admin has limited our app's access.
        """
        repos = self._gh_installation.get_repos()
        if self.teamname is not None:

            def team_can_see_repo(repo: Repository):
                return any(map(lambda team: team.name == self.teamname, repo.get_teams()))

            repos = [repo for repo in repos if team_can_see_repo(repo)]

        return repos
