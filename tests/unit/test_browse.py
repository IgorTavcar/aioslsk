from aioslsk.browse import BrowseDirectory, BrowseResult
from aioslsk.protocol.primitives import DirectoryData, FileData


def _file(leaf: str) -> FileData:
    """Builds a browse-style FileData (filename is the leaf name only)"""
    return FileData(1, leaf, 1, leaf.rsplit('.', 1)[-1], [])


def _dir(name: str, *leaves: str) -> DirectoryData:
    return DirectoryData(name=name, files=[_file(leaf) for leaf in leaves])


class TestBrowseResult:

    def test_buildsTreeFromFlatDirectories(self):
        directories = [
            _dir(r'@@root\Music', 'a.mp3'),
            _dir(r'@@root\Music\FLAC', 'b.flac'),
        ]

        result = BrowseResult.from_shares_reply('bob', directories)

        assert result.username == 'bob'
        # Raw directory lists are preserved untouched
        assert result.visible == directories
        assert result.locked == []

        music = result.get_directory(r'@@root\Music')
        assert music is not None
        assert music.name == r'@@root\Music'
        # In a browse response file names are leaf names only
        assert [f.filename for f in music.files] == ['a.mp3']
        assert set(music.subdirectories) == {'FLAC'}

    def test_filePaths_joinDirectoryAndLeaf(self):
        result = BrowseResult.from_shares_reply(
            'bob', [_dir(r'@@root\Music', 'a.mp3', 'b.mp3')])

        music = result.get_directory(r'@@root\Music')
        assert list(music.file_paths()) == [
            r'@@root\Music\a.mp3',
            r'@@root\Music\b.mp3',
        ]

    def test_iterFilePaths_isRecursiveAndFiltersLocked(self):
        visible = [
            _dir(r'@@root\Music', 'a.mp3'),
            _dir(r'@@root\Music\FLAC', 'b.flac'),
        ]
        locked = [_dir(r'@@root\Secret', 's.mp3')]

        result = BrowseResult.from_shares_reply('bob', visible, locked)

        assert list(result.iter_file_paths(include_locked=False)) == [
            r'@@root\Music\a.mp3',
            r'@@root\Music\FLAC\b.flac',
        ]
        assert list(result.iter_file_paths(include_locked=True)) == [
            r'@@root\Music\a.mp3',
            r'@@root\Music\FLAC\b.flac',
            r'@@root\Secret\s.mp3',
        ]

    def test_getDirectory_supportsForwardSlashes(self):
        result = BrowseResult.from_shares_reply('bob', [_dir(r'@@root\Music')])

        assert result.get_directory('@@root/Music') is not None

    def test_getDirectory_missingReturnsNone(self):
        result = BrowseResult.from_shares_reply('bob', [_dir(r'@@root\Music')])

        assert result.get_directory(r'@@root\Nope') is None

    def test_allFiles_isRecursive(self):
        directories = [
            _dir(r'@@root\Music', 'a.mp3'),
            _dir(r'@@root\Music\FLAC', 'b.flac'),
        ]

        result = BrowseResult.from_shares_reply('bob', directories)

        music = result.get_directory(r'@@root\Music')
        assert [f.filename for f in music.all_files()] == ['a.mp3', 'b.flac']
        # Non-recursive view: only the directory's own files
        assert [f.filename for f in music.files] == ['a.mp3']

    def test_lockedDirectoriesAreFlagged(self):
        visible = [_dir(r'@@root\Music', 'a.mp3')]
        locked = [_dir(r'@@root\Secret', 's.mp3')]

        result = BrowseResult.from_shares_reply('bob', visible, locked)

        assert result.locked == locked
        assert result.get_directory(r'@@root\Secret').is_locked is True
        assert result.get_directory(r'@@root\Music').is_locked is False

    def test_intermediateParentDirectoriesAreCreated(self):
        # Only the deep directory is returned; intermediate parents must still
        # be navigable.
        directories = [_dir(r'@@root\a\b\c', 'x.mp3')]

        result = BrowseResult.from_shares_reply('bob', directories)

        assert result.get_directory(r'@@root\a') is not None
        assert result.get_directory(r'@@root\a\b') is not None
        assert list(result.get_directory(r'@@root\a').file_paths()) == []
        assert list(result.get_directory(r'@@root\a\b\c').file_paths()) == [
            r'@@root\a\b\c\x.mp3',
        ]


class TestBrowseDirectory:

    def test_walkYieldsSelfThenDescendants(self):
        result = BrowseResult.from_shares_reply('bob', [
            _dir(r'@@root\Music'),
            _dir(r'@@root\Music\FLAC'),
        ])
        music = result.get_directory(r'@@root\Music')

        assert [d.name for d in music.walk()] == [r'@@root\Music', r'@@root\Music\FLAC']

    def test_getPath_emptyReturnsSelf(self):
        directory = BrowseDirectory(name='@@root')

        assert directory.get_path('') is directory
