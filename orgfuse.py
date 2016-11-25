#!/usr/bin/env python

import logging

from errno import ENOENT, EROFS, EIO
from stat import S_IFDIR, S_IFREG
from sys import argv, exit
from time import time
import re
import os

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
        return self._parse_tokens(tokens)[0]


NOW = time()


class FSTree():

    DIR_ATTRS = dict(st_mode=(S_IFDIR | 0o555), st_ctime=NOW,
                     st_mtime=NOW, st_atime=NOW, st_nlink=2,
                     st_uid=os.getuid(), st_gid=os.getgid())
    FILE_ATTRS = dict(st_mode=(S_IFREG | 0o444), st_ctime=NOW,
                      st_mtime=NOW, st_atime=NOW, st_nlink=1,
                      st_uid=os.getuid(), st_gid=os.getgid())

    @staticmethod
    def from_parse_tree(root):
        headline, _, section, children = root
        tree = FSTree(FSTree.DIR_ATTRS, headline)

        if section:
            section_attrs = FSTree.FILE_ATTRS.copy()
            section_content = "".join(section)
            section_attrs["st_size"] = len(section_content)
            section_node = FSTree(section_attrs, "section", section_content)
            tree.add_child(section_node)

        for child in children:
            tree.add_child(FSTree.from_parse_tree(child))

        return tree

    def __init__(self, attrs, name, content=None):
        self.attrs = attrs
        self.name = name
        self.content = content
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
        self.fd = 0

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        node = self.tree.find_path(path)
        if node is None:
            raise FuseOSError(EIO)
        return node.content[offset:offset + size]

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


HELP_MSG = """Usage: %s <orgfile> <mountpoint>

Mount an org-mode file as a directory.

Arguments:

  orgfile - an org-mode file to mount

  mountpoint - a directory to mount the file to"""

if __name__ == '__main__':
    if len(argv) != 3:
        print(HELP_MSG % argv[0])
        exit(1)

    org_file_path = argv[1]
    if not os.path.exists(org_file_path) or not os.path.isfile(org_file_path):
        print(HELP_MSG % argv[0])
        exit(1)

    mount_path = argv[2]
    if not os.path.exists(mount_path)or not os.path.isdir(mount_path):
        print(HELP_MSG % argv[0])
        exit(1)

    logging.basicConfig(level=logging.DEBUG)
    parse_tree = OrgFileParser(open(org_file_path, "r")).build_tree()
    fs_tree = FSTree.from_parse_tree(parse_tree)
    FUSE(FuseOperations(fs_tree), mount_path, foreground=True)
