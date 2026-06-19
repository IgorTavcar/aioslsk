from aioslsk.client import SoulSeekClient
from aioslsk.commands import (
    PeerGetSharesCommand,
    PeerGetUserInfoCommand,
)
from aioslsk.events import UserSharesReplyEvent, UserInfoUpdateEvent
from aioslsk.transfer.state import TransferState
from .mock.server import MockServer
from .fixtures import mock_server, client_1, client_2
from .utils import (
    wait_until_clients_initialized,
    wait_for_listener_awaited,
    wait_for_transfer_state,
)
import pytest
from unittest.mock import AsyncMock


class TestE2EPeer:

    @pytest.mark.asyncio
    async def test_get_shares(self, mock_server: MockServer, client_1: SoulSeekClient, client_2: SoulSeekClient):
        listener = AsyncMock()
        client_1.events.register(UserSharesReplyEvent, listener)
        await wait_until_clients_initialized(mock_server, amount=2)

        directories, locked_directories = await client_1.execute(
            PeerGetSharesCommand(client_2.settings.credentials.username),
            response=True
        )

        assert len(directories) > 0
        assert len(locked_directories) == 0

        event = await wait_for_listener_awaited(listener)

        assert isinstance(event, UserSharesReplyEvent)
        assert len(event.directories) > 0

    @pytest.mark.asyncio
    async def test_get_user_info(self, mock_server: MockServer, client_1: SoulSeekClient, client_2: SoulSeekClient):
        description = 'I am client 2'
        picture = bytes.fromhex('AABBCCDDEE')
        upload_slots = 5
        client_2.settings.credentials.info.description = description
        client_2.settings.credentials.info.picture = picture
        client_2.settings.transfers.limits.upload_slots = upload_slots

        listener = AsyncMock()
        client_1.events.register(UserInfoUpdateEvent, listener)
        await wait_until_clients_initialized(mock_server, amount=2)

        user_info = await client_1.execute(
            PeerGetUserInfoCommand(client_2.settings.credentials.username),
            response=True
        )
        assert user_info.description == description
        assert user_info.picture == picture
        assert user_info.upload_slots == upload_slots
        assert user_info.has_slots_free is True
        assert user_info.queue_length == 0

        event = await wait_for_listener_awaited(listener)

        assert isinstance(event, UserInfoUpdateEvent)
        assert event.current.description == description
        assert event.current.picture == picture
        assert event.current.upload_slots == upload_slots
        assert event.current.has_slots_free is True
        assert event.current.queue_length == 0

    @pytest.mark.asyncio
    async def test_browse_user(self, mock_server: MockServer, client_1: SoulSeekClient, client_2: SoulSeekClient):
        await wait_until_clients_initialized(mock_server, amount=2)

        result = await client_1.browse_user(
            client_2.settings.credentials.username)

        # The tree should be navigable and expose files with decodable attributes
        files = list(result.iter_files())
        assert len(files) > 0
        # All shares are EVERYONE, so nothing is locked
        assert all(not directory.is_locked for directory in result.root.walk())

        flac = next(f for f in files if f.filename.endswith('.flac'))
        attributes = flac.decode_attributes()
        assert attributes.is_lossless is True

    @pytest.mark.asyncio
    async def test_download_directory(
            self, mock_server: MockServer, client_1: SoulSeekClient,
            client_2: SoulSeekClient):
        client_1.network.set_download_speed_limit(100)
        client_2.network.set_upload_speed_limit(100)
        await wait_until_clients_initialized(mock_server, amount=2)

        username = client_2.settings.credentials.username
        result = await client_1.browse_user(username)

        # Locate the single-file album directory in the share tree
        album = next(
            directory for directory in result.root.walk()
            if directory.name.endswith('Cool_Test_Album')
        )

        transfers = await client_1.download_directory(username, album.name)

        assert len(transfers) == 1
        assert transfers[0].remote_path.endswith('Strange_Drone_Impact.mp3')

        await wait_for_transfer_state(transfers[0], TransferState.COMPLETE)
