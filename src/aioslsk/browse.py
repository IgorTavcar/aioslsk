"""High level, navigable view of a peer's shared files.

The Soulseek protocol returns a peer's shares (:class:`.PeerSharesReply`) as a
*flat* list of :class:`.DirectoryData`, where each entry's ``name`` is the full
(backslash separated) remote path of that directory. This module reconstructs
that flat list into a navigable tree so callers can drill into subdirectories,
walk the tree and collect files without having to parse paths themselves.
"""
from __future__ import annotations
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Optional

from .constants import PATH_SEPERATOR_PATTERN
from .protocol.primitives import DirectoryData, FileData


def _split_path(path: str) -> list[str]:
    """Splits a remote path into its components, ignoring empty parts (eg. from
    leading/trailing/duplicate separators)
    """
    return [part for part in PATH_SEPERATOR_PATTERN.split(path) if part]


@dataclass(slots=True)
class BrowseDirectory:
    """A single node in a browsed share tree"""
    name: str
    """Full (backslash separated) remote path of this directory. Empty for the
    synthetic root node
    """
    files: list[FileData] = field(default_factory=list)
    subdirectories: dict[str, 'BrowseDirectory'] = field(default_factory=dict)
    is_locked: bool = False

    def get_path(self, path: str) -> Optional['BrowseDirectory']:
        """Navigates to the (sub)directory at the given relative ``path``,
        returning ``None`` if no such directory exists

        :param path: path relative to this directory (separated by ``\\`` or ``/``)
        """
        node: Optional['BrowseDirectory'] = self
        for part in _split_path(path):
            assert node is not None
            node = node.subdirectories.get(part)
            if node is None:
                return None
        return node

    def walk(self) -> Iterator['BrowseDirectory']:
        """Yields this directory followed by all of its descendants (depth-first)"""
        yield self
        for child in self.subdirectories.values():
            yield from child.walk()

    def all_files(self) -> Iterator[FileData]:
        """Yields every file in this directory and all of its descendants"""
        for directory in self.walk():
            yield from directory.files

    def file_paths(self) -> Iterator[str]:
        """Yields the full remote paths of the files directly contained in this
        directory.

        In a browse response a file's :attr:`.FileData.filename` is only its
        leaf name; the full remote path (the form required to download the file)
        is the directory path joined with that leaf name.
        """
        for file in self.files:
            yield f'{self.name}\\{file.filename}' if self.name else file.filename


@dataclass(slots=True)
class BrowseResult:
    """Result of browsing a user, exposing both the navigable :attr:`root` tree
    and the raw ``visible``/``locked`` directory lists as returned by the peer
    """
    username: str
    root: BrowseDirectory
    visible: list[DirectoryData]
    locked: list[DirectoryData]

    @classmethod
    def from_shares_reply(
            cls, username: str, directories: list[DirectoryData],
            locked_directories: Optional[list[DirectoryData]] = None) -> 'BrowseResult':
        """Builds a :class:`BrowseResult` from the directory lists of a shares
        reply
        """
        locked_directories = locked_directories or []
        root = BrowseDirectory(name='')
        cls._insert(root, directories, is_locked=False)
        cls._insert(root, locked_directories, is_locked=True)
        return cls(
            username=username,
            root=root,
            visible=list(directories),
            locked=list(locked_directories)
        )

    @staticmethod
    def _insert(
            root: BrowseDirectory, directories: list[DirectoryData], is_locked: bool):
        for directory in directories:
            node = root
            accumulated: list[str] = []
            for part in _split_path(directory.name):
                accumulated.append(part)
                child = node.subdirectories.get(part)
                if child is None:
                    child = BrowseDirectory(name='\\'.join(accumulated))
                    node.subdirectories[part] = child
                node = child

            # `node` is now the leaf directory for this entry. Empty parent
            # directories are returned as separate entries and reach this point
            # too, harmlessly (re)assigning their (empty) file list.
            node.files = list(directory.files)
            node.is_locked = is_locked

    def get_directory(self, path: str) -> Optional[BrowseDirectory]:
        """Navigates to the directory at the given remote ``path``"""
        return self.root.get_path(path)

    def iter_files(self, include_locked: bool = True) -> Iterator[FileData]:
        """Yields every file across the whole tree

        :param include_locked: whether to include files from locked directories
        """
        for directory in self.root.walk():
            if directory.is_locked and not include_locked:
                continue
            yield from directory.files

    def iter_file_paths(self, include_locked: bool = True) -> Iterator[str]:
        """Yields the full remote path of every file across the whole tree
        (suitable for passing to a download)

        :param include_locked: whether to include files from locked directories
        """
        for directory in self.root.walk():
            if directory.is_locked and not include_locked:
                continue
            yield from directory.file_paths()
