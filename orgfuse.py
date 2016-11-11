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

    HEADLINE_TOKEN = 0
    SECTION_TOKEN = 1

    HEADLINE_RE = re.compile(r"(\*+) (.+)")

    def __init__(self, _file):
        self._lines = _file.readlines()

    def _tokenize(self, lines):
        cur_section_strs = []
        raw_tokens = [(self.HEADLINE_TOKEN, 0, "root")]
        depth = 0
        for line in lines:
            match = self.HEADLINE_RE.match(line)
            if match is None:
                cur_section_strs.append(line)
            else:
                if cur_section_strs:
                    section_token = (self.SECTION_TOKEN, depth, cur_section_strs)
                    raw_tokens.append(section_token)
                    cur_section_strs = []
                depth = len(match.group(1))
                headline_token = (self.HEADLINE_TOKEN, depth, match.group(2))
                raw_tokens.append(headline_token)
        else:
            if cur_section_strs:
                section_token = (self.SECTION_TOKEN, depth, cur_section_strs)
                raw_tokens.append(section_token)

        tokens = []
        for i, token in enumerate(raw_tokens):
            t_type, t_depth, t_section = raw_tokens[i]
            if t_type != self.HEADLINE_TOKEN:
                continue
            nt_type, nt_depth, nt_section = raw_tokens[i+1]
            headline = t_section
            depth = t_depth
            section = nt_section if nt_type == self.SECTION_TOKEN else None
            tokens.append((headline, depth, section))

        return tokens

    def _parse_tokens(self, tokens):
        res = []
        while tokens:
            headline, depth, section = tokens[0]
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

            res.append((headline, depth, section, children))
        return res

    def build_tree(self):
        tokens = self._tokenize(self._lines)
        parse_tree = self._parse_tokens(tokens)[0]

        from pprint import pprint
        pprint(tokens)
        pprint(parse_tree)

        return FSTree.from_parse_tree(parse_tree)


NOW = time()

class FSTree():

    DIR_ATTRS = dict(st_mode=(S_IFDIR | 0o755), st_ctime=NOW,
                     st_mtime=NOW, st_atime=NOW, st_nlink=2)
    FILE_ATTRS = dict(st_mode=(S_IFREG | 0o755), st_ctime=NOW,
                      st_mtime=NOW, st_atime=NOW, st_nlink=1)

    @staticmethod
    def from_parse_tree(root):
        headline, _, section, children = root
        tree = FSTree(FSTree.DIR_ATTRS, headline)
        tree.add_child(FSTree(FSTree.FILE_ATTRS, "section"))
        for child in children:
            tree.add_child(FSTree.from_parse_tree(child))
        return tree

    def __init__(self, attrs, name):
        self.attrs = attrs
        self.name = name
        self.children = {}

    def add_child(self, child):
        self.children[child.name] = child

    def find_path(self, path):
        return self._find_path(self._convert_path(path))

    def _find_path(self, path):
        if len(path) == 0:
            return self
        left_path = path[0]
        if left_path == "":
            return self
        if left_path in self.children:
            return self.children[left_path]._find_path(path[1:])
        return None

    def _convert_path(self, path):
        return path.lstrip("/").split("/")

    def get_attrs(self):
        return self.attrs

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
        return node.get_attrs()

if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)

    logging.basicConfig(level=logging.DEBUG)
    org_str = """
just text
* headline 1
headline section 1
** inner headline 1
some inner section 1
some inner section 1-2
** inner headline 2
inner section 2
** inner headline 3
*** inner inner section 1
* headline 2
section text 2
"""
    print(org_str)
    strio = StringIO(org_str)
    parser = OrgFileParser(strio)
    document_tree = parser.build_tree()
    fuse = FUSE(FuseOperations(document_tree), argv[1], foreground=True)
