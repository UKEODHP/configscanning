"""This scanner is for testing. It simply lists the names of the files it's asked to scan,
one per line, adding them to visited_files"""

visited_files = []


class Scanner:
    def __init__(self, **kwargs):
        pass

    def scan_file(self, fname, data):
        visited_files.append(fname)
