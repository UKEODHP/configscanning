import argparse
import json
import logging
import os

import pulsar
import requests

from configscanning import comparefiles, repoupdater


def combine_arguments(args1, args2, additional_arguments=None):
    if additional_arguments is None:
        additional_arguments = {}

    parser = argparse.ArgumentParser()

    for key in additional_arguments:
        parser.add_argument(f"--{key}", default=additional_arguments[key])

    for namespace in (args1, args2):
        arguments = vars(namespace)
        for arg in arguments.keys():
            if arg not in [x.dest for x in parser._actions]:
                parser.add_argument(f"--{arg}", default=arguments[arg])

    return parser


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("configscanning").setLevel(logging.DEBUG)

    parser_repoupdater = repoupdater.get_parser()
    parser_comparefiles = comparefiles.get_parser()

    args_repoupdater, _ = parser_repoupdater.parse_known_args()
    args_comparefiles, _ = parser_comparefiles.parse_known_args()

    repoupdater_arguments = vars(args_repoupdater)

    folder_arguments = {"clone_dir": repoupdater_arguments["dest"]}

    if vars(args_comparefiles)["s3_folder"] is None:
        repo_url = requests.urllib3.util.parse_url(repoupdater_arguments["repourl"])
        branch = repoupdater_arguments["branch"]

        folder_arguments["s3_folder"] = f"{repo_url.path}/{branch}".lstrip("/")

    parser = combine_arguments(
        args_repoupdater, args_comparefiles, additional_arguments=folder_arguments
    )

    client = pulsar.Client(os.environ.get("PULSAR_URL"))
    producer = client.create_producer(topic="harvester", producer_name="git_change_scanner")

    try:
        logging.info("Checking for updates in GitHub repository")
        repoupdater.main(parser)
        logging.info("Pushing changes to S3 bucket")
        file_summary = comparefiles.main(parser)
        logging.info("Bucket synchronised")

        msg = json.dumps(file_summary)
        producer.send(msg.encode("utf-8"))
    except Exception:
        msg = "Harvester error"
        producer.send(msg.encode("utf-8"))
    finally:
        producer.close()
        client.close()
        logging.debug("Complete")


if __name__ == "__main__":
    main()
