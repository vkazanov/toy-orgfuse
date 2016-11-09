#!/usr/bin/env python
from __future__ import print_function, absolute_import, division

import logging

from collections import defaultdict
from errno import ENOENT, EROFS
from stat import S_IFDIR, S_IFLNK, S_IFREG
from sys import argv, exit
from time import time
from StringIO import StringIO
import re

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

class OrgFileParser():

    HEADER_TOKEN = 0
    TEXT_TOKEN = 1

    HEADER_RE = re.compile(r"(\*+) (.+)")

    def __init__(self, _file):
        self._lines = _file.readlines()

    def _tokenize(self, lines):
        tokens = []
        cur_body_strs = []
        for line in lines:
            from pprint import pprint
            print("LINE:")
            pprint(line)
            match = self.HEADER_RE.match(line)
            if match is None:
                cur_body_strs.append(line)
            else:
                if cur_body_strs:
                    text_token = (self.TEXT_TOKEN, None, cur_body_strs)
                    tokens.append(text_token)
                    cur_body_strs = []
                header_token = (self.HEADER_TOKEN, len(match.group(1)), match.group(2))
                tokens.append(header_token)
        else:
            if cur_body_strs:
                text_token = (self.TEXT_TOKEN, None, cur_body_strs)
                tokens.append(text_token)

        return tokens

    def build_tree(self):
        tokens = self._tokenize(self._lines)
        from pprint import pprint
        print("TOKENS:")
        pprint(tokens)

        root = OrgTree(OrgTree.DIR, "")
        root.add_child(OrgTree(OrgTree.FILE, "test1"))
        root.add_child(OrgTree(OrgTree.FILE, "test2"))

        child = OrgTree(OrgTree.DIR, "test3")
        child.add_child(OrgTree(OrgTree.FILE, "test4"))
        child.add_child(OrgTree(OrgTree.FILE, "test5"))

        root.add_child(child)
        return root

class OrgTree():

    DIR = 0
    FILE = 1

    def __init__(self, _type, name):
        self.type = _type
        self.name = name
        self.children = {}

    def add_child(self, child):
        self.children[child.name] = child

    def _build_path(self, path):
        return path.lstrip("/").split("/")

    def find_path(self, path):
        return self._find_path(self._build_path(path))

    def _find_path(self, path):
        if len(path) == 0:
            return self
        left_path = path[0]
        if left_path == "":
            return self
        if left_path in self.children:
            return self.children[left_path]._find_path(path[1:])
        return None

NOW = time()

DIR_ATTRS = dict(st_mode=(S_IFDIR | 0o755), st_ctime=NOW,
                 st_mtime=NOW, st_atime=NOW, st_nlink=2)
FILE_ATTRS = dict(st_mode=(S_IFREG | 0o755), st_ctime=NOW,
                               st_mtime=NOW, st_atime=NOW, st_nlink=1)

class OrgTreeFS(LoggingMixIn, Operations):

    def __init__(self, tree):
        self.tree = tree
        self.data = defaultdict(str)
        self.fd = 0

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        return self.data[path][offset:offset + size]

    def readdir(self, path, fh):
        node = self.tree.find_path(path)
        if node is None:
            raise FuseOSError(EROFS)
        return ['.', '..'] + [child for child in node.children]

    def getattr(self, path, fh=None):
        node = self.tree.find_path(path)
        if node is None:
            raise FuseOSError(ENOENT)
        if node.type == OrgTree.DIR:
            return DIR_ATTRS
        else:
            return FILE_ATTRS

if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)

    logging.basicConfig(level=logging.DEBUG)
    org_str = """
* header 1
header text
** inner header 1
some inner text 1
** inner header 2
inner text2
** inner header 3
*** inner inner header 1
"""
    print(org_str)
    strio = StringIO(org_str)
    parser = OrgFileParser(strio)
    tree = parser.build_tree()
    # fuse = FUSE(OrgTreeFS(tree), argv[1], foreground=True)
