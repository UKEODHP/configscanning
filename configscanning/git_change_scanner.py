import argparse
import requests
import tempfile

from configscanning import repoupdater, comparefiles


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
    parser_repoupdater = repoupdater.get_parser()
    parser_comparefiles = comparefiles.get_parser()

    args_repoupdater, _ = parser_repoupdater.parse_known_args()
    args_comparefiles, _ = parser_comparefiles.parse_known_args()

    repoupdater_arguments = vars(args_repoupdater)

    folder_arguments = {'clone_dir': repoupdater_arguments['dest']}

    if vars(args_comparefiles)['s3_folder'] is None:
        repo_url = requests.urllib3.util.parse_url(repoupdater_arguments['repourl'])
        branch = repoupdater_arguments['branch']

        folder_arguments['s3_folder'] = f"{repo_url.path}/{branch}".lstrip('/')

    parser = combine_arguments(args_repoupdater, args_comparefiles, additional_arguments=folder_arguments)



    repoupdater.main(parser)
    comparefiles.main(parser)


if __name__ == '__main__':
    main()


