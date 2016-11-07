#!/usr/bin/env python
from __future__ import print_function, absolute_import, division

import logging

from collections import defaultdict
from errno import ENOENT, EROFS
from stat import S_IFDIR, S_IFLNK, S_IFREG
from sys import argv, exit
from time import time

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

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
        print(path)
        node = self.tree.find_path(path)
        print(path, " ->", node)
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

    tree = OrgTree(OrgTree.DIR, "")
    tree.add_child(OrgTree(OrgTree.FILE, "test1"))
    tree.add_child(OrgTree(OrgTree.FILE, "test2"))

    dir_child = OrgTree(OrgTree.DIR, "test3")
    dir_child.add_child(OrgTree(OrgTree.FILE, "test4"))
    dir_child.add_child(OrgTree(OrgTree.FILE, "test5"))

    tree.add_child(dir_child)

    fuse = FUSE(OrgTreeFS(tree), argv[1], foreground=True)
