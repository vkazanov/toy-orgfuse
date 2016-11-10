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
        cur_body_strs = []
        raw_tokens = [(self.HEADER_TOKEN, 0, "root")]
        depth = 0
        for line in lines:
            match = self.HEADER_RE.match(line)
            if match is None:
                cur_body_strs.append(line)
            else:
                if cur_body_strs:
                    text_token = (self.TEXT_TOKEN, depth, cur_body_strs)
                    raw_tokens.append(text_token)
                    cur_body_strs = []
                depth = len(match.group(1))
                header_token = (self.HEADER_TOKEN, depth, match.group(2))
                raw_tokens.append(header_token)
        else:
            if cur_body_strs:
                text_token = (self.TEXT_TOKEN, depth, cur_body_strs)
                raw_tokens.append(text_token)

        tokens = []
        for i, token in enumerate(raw_tokens):
            t_type, t_depth, t_body = raw_tokens[i]
            if t_type != self.HEADER_TOKEN:
                continue
            nt_type, nt_depth, nt_body = raw_tokens[i+1]
            title = t_body
            depth = t_depth
            body = nt_body if nt_type == self.TEXT_TOKEN else None
            tokens.append((title, depth, body))

        return tokens

    def _parse_tokens(self, tokens):
        res = []
        while tokens:
            title, depth, body = tokens[0]
            tokens = tokens[1:]

            child_tokens = []
            for i, token in enumerate(tokens):
                _, child_depth, _ = token
                if child_depth <= depth:
                    child_tokens = tokens[:i]
                    tokens = tokens[i:]
                    break
            else:
                child_tokens = tokens
                tokens = []

            children = self._parse_tokens(child_tokens)

            res.append((title, depth, body, children))
        return res

    def build_tree(self):
        tokens = self._tokenize(self._lines)
        parse_tree = self._parse_tokens(tokens)[0]

        from pprint import pprint
        pprint(tokens)
        pprint(parse_tree)

        return FSTree.from_parse_tree(parse_tree)

class FSTree():

    DIR = 0
    FILE = 1

    @staticmethod
    def from_parse_tree(root):
        title, _, body, children = root
        tree = FSTree(FSTree.DIR, title)
        tree.add_child(FSTree(FSTree.FILE, "body"))
        for child in children:
            tree.add_child(FSTree.from_parse_tree(child))
        return tree

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

class FuseOperations(LoggingMixIn, Operations):

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
        if node.type == FSTree.DIR:
            return DIR_ATTRS
        else:
            return FILE_ATTRS

if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)

    logging.basicConfig(level=logging.DEBUG)
    org_str = """
just text
* header 1
header text 1
** inner header 1
some inner text 1
some inner text 1-2
** inner header 2
inner text2
** inner header 3
*** inner inner header 1
* header 2
header text 2
"""
    print(org_str)
    strio = StringIO(org_str)
    parser = OrgFileParser(strio)
    tree = parser.build_tree()
    fuse = FUSE(FuseOperations(tree), argv[1], foreground=True)
