# UKEODHP service-manager-config-scanner

This is the UKEODHP config scanner. It is a platform for creating machine learning models.

This component has the following responsibilities:
* To synchronize git repositories connected to Workspaces into a persistent volume in the platform.
* To scan these repositories for configuration files which the platform must process, and which define the Models,
  Workflows and Applications which must be deployed.
* To process this configuration and create/manage Model, Workflow and Application kubernetes CRs.


# Getting started for development

You will need Python 3.11. On Debian you may need:
* `apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys F23C5A6CF475977595C89F51BA6932366A755776`
* `sudo add-apt-repository -y 'deb http://ppa.launchpad.net/deadsnakes/ppa/ubuntu focal main'` (or `jammy` in place of 
  `focal` for later Debian)
* `sudo apt update`
* `sudo apt install python3.11 python3.11-venv`

and on Ubuntu you may need
* `sudo add-apt-repository -y 'ppa:deadsnakes/ppa'`
* `sudo apt update`
* `sudo apt install python3.11 python3.11-venv`

then:

* `virtualenv venv -p python3.11`
* `. venv/bin/activate`
* `rehash`
* `python -m ensurepip -U`
* `pip3 install -r requirements.txt -r requirements-dev.txt`

To modify the requirements edit `pyproject.toml` and run first `pip-compile`, then 
`pip-compile --extra dev -o requirements-dev.txt`. The second should only be necessary if you modify the dev 
dependencies.

# Formatting and linting

The project is formatted with black, run `black --line-length 100 .` to reformat or use an editor integration.
A GitHub workflow will reformat what you commit.

The project is also linted with ruff, run `ruff .` or use an editor integration. The GitHub workflow will also
run this.

# Testing

Run `pytest` to test. Beware that this will talk to GitHub and check out some repos in a temporary directory, so running
this with `--looponfail` may be undesirable (unless you exclude tests marked `integrationtest`).

To test the Docker build, use `make testdocker`.

# Building for deployment

You will need to be logged into ECR (see 'Configure AWS ECR' in argocd-deployment/README.md).

Then build, tag and push the image:
* `git tag <version>` (if version is not 'latest')
* `make dockerbuild dockerpush VERSION=<version>` (default version is 'latest')
