# aioslsk digest (agent-optimized, dense)

Condensed ground-truth for the **soulshelf fork of aioslsk v1.6.3**. Companion to `index.html` (human doc); every fact cites `file:line` in `src/aioslsk/`. Telegraphic by design. Fork = upstream v1.6.3 + 6 logging downgrades, NO logic changes (see §FORK).

Notation: `→` = leads to / returns; `A.b:NN` = file `A/b.py` line NN; planes = server / peer(P) / file(F) / distributed(D).

---

## CORE OBJECTS
- `SoulSeekClient` facade `client.py:46`; ctor wires managers in fixed order `client.py:52-96` via `create_*`. 4 injected primitives: `Settings`(pydantic `settings.py:181`), `EventBus`(`events.py:118`), `Network`(`network/network.py:160`), `Session`(`session.py:7`, None until login).
- Managers (all `BaseManager` `base_manager.py:5`, hooks `load_data/store_data/start/stop`→`list[Task]`): users `user/manager.py:105`, rooms `room/manager.py:62`, interests `interest/manager.py:33`, shares `shares/manager.py:146`, transfers `transfer/manager.py:86`, peers `peer.py:33`, searches `search/manager.py:57`, server `server.py:16`. 8 collected in `self.services` `client.py:84-93`.
- `distributed_network` (`distributed.py:72`) is a BaseManager but **NOT in services** — purely event-driven; only `stop()` reached, never `load_data/start`. Same for `Network`.
- Ctor-order dependency: transfers gets users+shares; searches/peers get shares+transfers; `TransferManager` IS the `UploadInfoProvider` (`transfer/interface.py:4`) passed as `upload_info_provider`.
- Versions: `CLIENT_VERSION=157`, `MINOR_VERSION=100` `client.py:39-40`. Server default `server.slsknet.org:2416` `settings.py:57-58`.

## LIFECYCLE  (start→connect→login→run_until_stopped→stop)
- `start(connect=True)` `client.py:107`: set loop exc-handler, make `_stop_event`, gather `load_data()` then `start()` over services, scan if `shares.scan_on_start` `client.py:126`, then `connect()`.
- `connect()` `client.py:158`→`network.initialize()` `network.py:235`: `connect_listening_ports()` then `connect_server()` (30s timeout `SERVER_CONNECT_TIMEOUT` `constants.py:20`).
- `login()` `client.py:164-212`: send `Login.Request`, **synchronously** `receive_message_object()` the `Login.Response` (bypasses dispatch loop, no handlers fire), `AuthenticationError` on `!success` `client.py:191`, build `Session`, emit `SessionInitializedEvent`, **then** `start_reader_task()` `client.py:212`. ⇒ async server events only begin AFTER session init.
- `run_until_stopped()` `client.py:132` = await `_stop_event`. `stop()` `client.py:138`: set event, `network.disconnect()`, gather `stop()`+await cancelled tasks, gather `store_data()` (writes transfer+shares caches).
- Async-CM `__aenter__/__aexit__`=start/stop `client.py:226` — does NOT login.
- Auto re-login: `ServerReconnectedEvent`→`login()` iff `network.server.reconnect.auto` `client.py:384`. Server CLOSED→null session+`SessionDestroyedEvent` `client.py:376-382`.

## SETTINGS  (`settings.py`, pydantic `validate_assignment=True` everywhere → bad runtime assign raises immediately)
- **NO .env loading**: no `SettingsConfigDict/env_file/env_prefix/env_nested_delimiter`. Construct in code: `Settings(credentials=CredentialsSettings(username=, password=))`. Persist via `model_dump(mode="json")` / `model_validate`. `generate` CLI just dumps JSON from --username/--password.
- credentials.username/password (required; `are_configured()`=username truthy & password not None `settings.py:96`); credentials.info.description/.picture.
- network.server.hostname/port (`settings.py:57-58`); .reconnect.auto=False/.timeout=10 (`:52-53`).
- network.listening.port=60000 / .obfuscated_port=60001 / .error_mode=CLEAR (`:63-65`). CLEAR raises only if non-obf port fails; ALL=if every port fails; ANY=if any fails `network.py:264-277`.
- network.peer.obfuscate=False / .connect_mode=RACE (`:69-70`). network.upnp.enabled=True. network.limits.upload_speed_kbps/download_speed_kbps=0 (0=unlimited).
- shares.scan_on_start=True; shares.download=`os.getcwd()` at import (SET EXPLICITLY) `:149`; shares.directories[] (path, share_mode=EVERYONE, users).
- searches.send.store_results=True `:102`; .request_timeout=0 / .wishlist_request_timeout=-1; searches.receive.store_amount=500; .max_results=100 (alias `searches.max_results`).
- transfers.limits.upload_slots=2 `:139`; transfers.report_interval=0.250s `:144`.
- users.friends:set[str]; users.blocked:dict[str,BlockingFlag] (plain list auto→{name:ALL}); rooms.auto_join/private_room_invites=True + favorites. interests.liked/hated. debug.search_for_parent=True / .ip_overrides / .log_connection_count.

## EVENTBUS  (`events.py:118`)
- `register(event_class, listener, priority=100)` `:125` exact-class match (Event ≠ subclasses); lower priority first (list re-sorted each register). `unregister` by equality. `emit(event)` async (awaits coro listeners, calls sync inline, ordered). `emit_sync` sync-only (skips+warns async listeners).
- **WEAKREF FOOTGUN** `:130-136`: listeners stored as `weakref.ref` / `weakref.WeakMethod`(bound methods). Bare lambda/closure/bound-method-of-unretained-object is GC'd → `_remove_callback` `:211` purges it → silently stops firing, no error. FIX: keep a strong ref (attr on long-lived obj / variable / list). Lib managers survive only because client holds them.
- Both emit paths wrap each listener in try/except+`logger.exception` — exceptions swallowed to log, never reach emitter.
- `InternalEvent` marker `:618` = lib-internal wiring (still listenable).
- Most-used events: `SessionInitializedEvent`(session, raw=Login.Response) `:227`; `SessionDestroyedEvent` `:234`; `SearchRequestSentEvent` `:477`; `SearchResultEvent`(query:SearchRequest, result:SearchResult) `:489`; `SearchRequestRemovedEvent` `:483`; `SearchRequestReceivedEvent`(username,query,result_count = WE were searched) `:496`; `TransferAddedEvent` `:589`/`TransferRemovedEvent` `:595`; `TransferProgressEvent`(updates:list[(Transfer,prev,cur)]) `:601`; `UserStatusUpdateEvent` `:303`/`UserStatsUpdateEvent` `:313`/`UserInfoUpdateEvent` `:322`; `RoomMessageEvent` `:336`/`RoomJoinedEvent` `:367`/`RoomLeftEvent` `:379`; `PrivateMessageEvent` `:458`; `UserSharesReplyEvent`(directories, locked_directories) `:571`; `ScanCompleteEvent`(internal) `:656`.
- `SharedDirectoryChangeEvent` emitted via `emit_sync` `shares/manager.py:416` ⇒ async listeners for it are dropped.

## WIRE PROTOCOL  (`protocol/primitives.py` machinery, `protocol/messages.py` ~2254 defs; all little-endian `<`)
- Frame = `uint32 length` + `code` + payload. length = `len(message_id)+len(message)` (excludes itself) `primitives.py:409`. Code read at offset 4, length discarded `primitives.py:427`.
- Code width by plane: server=uint32 `messages.py:53,64`; peer=uint32 `:94`; **peer-init=uint8** `:79`; **distributed=uint8** `:109`.
- FILE plane ('F'): NO framed messages. After init: bare `uint32 ticket` (`receive_transfer_ticket` `connection.py:648`) → bare `uint64 offset` (`:666`) → raw byte stream (`receive_file/send_file` `:705/:739`), zero framing.
- Primitives `primitives.py`: uint8`<B`:86, uint16`<H`:100, uint32`<I`:114, uint64`<Q`:128, int32`<i`:142, boolean`<?`:218, string(uint32 len+UTF-8, falls back cp1252 on decode err):156/168, bytearr:183, ipaddr(`<4s`, byte-REVERSED both ends):200, array(uint32 count+N elems):232. `deserialize(pos,data)→(new_pos,value)` cursor contract.
- Composites: `Attribute`(frozen, 2×uint32 key/value, hand-packed `_ATTR_STRUCT='<II'`) `:451`; `FileData`(unknown:uint8, filename:string, filesize:uint64, extension:string, attributes:array[Attribute]) hand-rolled `:505-543`; `DirectoryData`(name:string, files:array[FileData]) `:559`.
- `AttributeKey` `:71`: BITRATE=0, DURATION=1, VBR=2, SAMPLE_RATE=4, BIT_DEPTH=5 (3 absent). `FileData.get_attribute_map()→dict[AttributeKey,int]` `:545`, silently drops unknown keys. Heuristic: BITRATE(±VBR)=lossy/mp3; SAMPLE_RATE+BIT_DEPTH=lossless/flac; many peers omit → treat sparse.
- `ProtocolDataclass` `:259` generic engine; fields = `field(metadata={'type','subtype','if_true','if_false','optional'})` in wire order, cached `_CACHED_FIELDS`. `if_true/if_false`=conditional on sibling truthiness (Login.Response gates `messages.py:149-153`); `optional`=trailing, deserialized only if bytes remain / serialized only if not None.
- `MessageDataclass` `:377`: `MESSAGE_ID:ClassVar[uint8|uint32]`; serialize id→body→(opt zlib)→length+id+body; deserialize reads/discards length, reads id (type-driven width), `ValueError` on id mismatch, **warns on trailing bytes** `:439` (NOT downgraded).
- Dispatch = linear scan over `__subclasses__()` matching MESSAGE_ID; no match → `UnknownMessageError`. Entry pts: `ServerMessage.deserialize_request/_response`, `{PeerInitialization,Peer,Distributed}Message.deserialize_request`.
- Quirks: `_PeerInitTicket(uint32)` falls back uint64 if >4 bytes remain `messages.py:1821`. `DistributedServerSearchRequest` is distributed yet uint32 id 0x5D `:2249` (deprecated; re-translate).
- **Compression** zlib, per-message, payload-only (length+id stay plaintext). Opt-in via override default True. Compressed: `PeerSharesReply` 0x05 `:1910`, `PeerSearchReply` 0x09 `:1959`, `PeerDirectoryContentsReply` 0x25 `:2040`.
- **Obfuscation** `protocol/obfuscation.py`: KEY_SIZE=4, rolling-XOR. Obf frame = 4B plain key + enc(length) + enc(code+payload), HEADER_SIZE_OBFUSCATED=8 vs _UNOBFUSCATED=4 `connection.py:50-51`. **Only 'P' connections stay obfuscated** — `PeerConnection.set_connection_state` forces `obfuscated=False` for non-PEER on leaving AWAITING_INIT `connection.py:634`. Server plane can be obf (`network.py:225/231`).
- Read path: `_message_reader_loop` `connection.py:297` → `receive_message_object` `:398` → `_read_message`(reads header_size, de-obf header→len, readexactly body) `:374` → `decode_message_data`(de-obf, deserialize) `:529` → `_perform_message_callback` `:566`. Send: `send_message` `:476` (skips silently if closing), serialize→obf→write w/10s drain.
- Error path: failures → `MessageDeserializationError(proto_message)` `:540`. Reader loop catches: `ConnectionReadError`(log+continue), `MessageDeserializationError`(log+continue, no teardown), falsy msg=EOF→return. `CloseReason`: UNKNOWN/CONNECT_FAILED/REQUESTED/READ_ERROR/WRITE_ERROR/TIMEOUT/EOF `:68-75`.

## SERVER MESSAGES  (id | dir; →send / ←recv). `network.send_server_messages(*m)` (awaits, raises) / `queue_server_messages` (f&f).
Login 0x01 →/←; SetListenPort 0x02 →; GetPeerAddress 0x03 →/← (ip 0.0.0.0=offline); AddUser 0x05 →/← (server then auto-pushes status/stats); RemoveUser 0x06 →; GetUserStatus 0x07 →/←; RoomChatMessage 0x0D →/←; JoinRoom 0x0E →/←; LeaveRoom 0x0F →; ConnectToPeer 0x12 →/← (indirect brokering); PrivateChatMessage 0x16 →/← (+Ack 0x17 → or server resends); FileSearch 0x1A →/← (global out; inbound room/user-targeted); SetStatus 0x1C → (0=off,1=away,2=on); Ping 0x20 → (5min keepalive); SharedFoldersFiles 0x23 →; GetUserStats 0x24 →/←; Kicked 0x29 ←; UserSearch 0x2A →; RoomList 0x40 →/← (auto after logon); PrivilegedUsers 0x45 ←; CheckPrivileges 0x5C →/←; ServerSearchRequest 0x5D ← (forward to dist children); AcceptChildren 0x64 →; PotentialParents 0x66 ←; WishlistSearch 0x67 →; WishlistInterval 0x68 ←; RoomSearch 0x78 →.
- Login.Request fields: username,password,client_version=157,md5hash=`calc_md5(username+password)`,minor_version=100 `messages.py:136`. Response: success + (if success) greeting,ip(your external IP),md5hash,privileged ; (else) reason `:145-153`.
- After login server pushes: WishlistInterval, RoomList, PrivilegedUsers, ParentMinSpeed, ParentSpeedRatio, MinParentsInCache, DistributedAliveInterval, PotentialParents.
- `advertise_listening_ports()` `network.py:329` sends `SetListenPort(port, obfuscated_port_amount=1 if obf else 0, obfuscated_port)` on `SessionInitializedEvent`. `get_listening_ports()` returns 0 for any port not CONNECTED.
- ServerConnection read timeout `SERVER_READ_TIMEOUT=600s`(=2 ping cycles); ping every `SERVER_PING_INTERVAL=300s` via ServerManager BackgroundTask (start on CONNECTED, cancel on CLOSING `server.py:54-62`).
- **Watchdog** (reconnect): 0.5s BackgroundTask `network.py:199`, started only if reconnect.auto & CONNECTED, acts only when socket CLOSED, sleeps timeout then `connect_server()`→`ServerReconnectedEvent`. **EOF means STOP** (banned/dup-login) — watchdog cancelled, no reconnect `:1066-1069` (reconnecting while banned extends ban). No creds → log once, give up.

## PEER CONNECTIONS  (`network.create_peer_connection` `network.py:522`; reuse via `get_peer_connection` `:649`)
- Types `PeerConnectionType` `connection.py:54`: PEER 'P' (shares/userinfo/search-replies/transfer-negotiation, default), FILE 'F' (one socket/transfer; ticket+offset+raw bytes), DISTRIBUTED 'D' (search tree). Type drives: read-framing, id-width, obfuscation (only P).
- Init handshake (1 msg in AWAITING_INIT `connection.py:609`): `PeerInit.Request`(uint8 0x01; username,typ,ticket) sent by **direct dialer** right after TCP `network.py:835`; `PeerPierceFirewall.Request`(uint8 0x00; ticket) sent by **indirect callback dialer** to prove which ConnectToPeer it fulfils `:930`.
- Inbound `on_peer_accepted` `network.py:1079`: PeerInit→copy username/typ, finalize, `PeerInitializedEvent(requested=False)`; PierceFirewall→lookup `_expected_connection_futures[ticket]`, copy stored username/typ, `PeerInitializedEvent(requested=True)`, resolve future; unknown ticket / other → warn+disconnect.
- `_finalize_peer_connection` `:947`: 'F'→NEGOTIATING_TRANSFER + attach rate limiters; else→ESTABLISHED (starts reader loop). 'F' has NO reader loop — transfer code drives socket synchronously.
- **Direct** `_make_direct_connection` `:806`: if no ip/port, `GetPeerAddress` → `_get_peer_address` `:625` (0.0.0.0/no-port → `PeerConnectionError`); connect, send PeerInit. Works only if peer reachable inbound from us.
- **Indirect** `_make_indirect_connection` `:850`: register `PeerFuture(ticket,username,typ)` + CannotConnect future, send `ConnectToPeer.Request(ticket,username,typ)`, `asyncio.wait(FIRST_COMPLETED, PEER_INDIRECT_CONNECT_TIMEOUT=60s)`. timeout/empty→error; CannotConnect done→error; else return PeerFuture's conn. Works only if WE reachable inbound.
- Fulfil others' indirect: server `ConnectToPeer.Response`→`_on_connect_to_peer` `:794` spawns `_handle_connect_to_peer` `:905`: dial requester, send PierceFirewall, `PeerInitializedEvent(requested=False)`; on dial fail → `CannotConnect.Request` + raise.

## DISTRIBUTED SEARCH  (`distributed.py:72`; event-driven, NOT in services)
- Tree: ≤1 parent, ≤`_max_children` children. Server seeds branch roots → flood parent→child → **results go DIRECT peer-to-peer to original searcher, NEVER up the tree**.
- `DistributedPeer`(username, connection[D], branch_level, branch_root) `:62`. State on manager: parent/children/potential_parents(deque maxlen 20)/distributed_peers/parent_min_speed/parent_speed_ratio/_max_children(5)/_accept_children(True) `:83-99`.
- Msgs: server→client ParentMinSpeed 0x53, ParentSpeedRatio 0x54, ServerSearchRequest 0x5D(distributed_code,unknown,username,ticket,query), PotentialParents 0x66, ResetDistributed 0x82; client→server ToggleParentSearch 0x47, AcceptChildren 0x64, BranchLevel 0x7E, BranchRoot 0x7F; parent→child(D) DistributedSearchRequest D:0x03(unknown=0x31,username,ticket,query), DistributedBranchLevel D:0x04, DistributedBranchRoot D:0x05; child→parent DistributedChildDepth D:0x07(deprecated); DistributedServerSearchRequest D:0x5D(deprecated, re-translate to D:0x03).
- Find parent: on session init `ToggleParentSearch(True)` `:581`. `PotentialParents`→cache usernames, dial each as type-D concurrently `:369`. Candidate becomes parent only after BOTH branch_level AND branch_root set → `_check_if_new_parent` `:205` (explicit None-checks, level can be 0; level==0 ⇒ self is own root `:434`). `_set_parent` `:174`: cancel potential-parent tasks, disconnect all type-D that aren't parent/child, notify server + children. Advertised values `_get_advertised_branch_values` `:119`: no parent/we-are-root → level 0, root=us; else level=parent.level+1, root=parent.root.
- Accept child `_check_if_new_child` `:274`: reject if username in potential_parents (cycle), if `!_accept_children`, if `len(children)>=_max_children`. Capacity recomputed on our GetUserStats: speed<parent_min_speed*1024→0 children; else `_max_children=speed/((parent_speed_ratio/10)*1024)` `:559`. Defaults MIN_SPEED=1, RATIO=50.
- Propagate down (all → `send_messages_to_children`): from server `_on_server_search_request` `:395` (skip own query, wrap into D:0x03); from parent `_on_distributed_search_request` `:486` (re-broadcast unchanged); from buggy root D:0x5D → re-pack if inner code==0x03.
- **Same 3 msgs ALSO consumed by SearchManager** (separate @on_message on same bus) → `_query_shares_and_reply(ticket,username,query)` `search/manager.py:340`: one inbound search both propagates (DistributedNetwork) AND triggers local share lookup (SearchManager).
- Reply: matches → open DIRECT conn to original searcher, send single `PeerSearchReply.Request`(username=us, ticket, results=convert_items_to_file_data(visible,full_path), has_slots_free, avg_speed, queue_size, locked_results) `search/manager.py:185`. Empty results → no dial. Blocked users skipped.
- Parent close → `_unset_parent` (parent=None, re-enable search, tell children level 0/own root). ResetDistributed → `reset()` (drop parent+children).

## SEARCH SUBSYSTEM  (`search/manager.py`, `search/model.py`)  — FIRE-AND-FORGET, no completion signal
- Two entry styles: **manager methods** `search()/search_room()/search_user()` `:114/:136/:161` (async, register request, attach timeout timer, emit SearchRequestSentEvent, RETURN SearchRequest — PREFER THESE); **commands** `GlobalSearchCommand/UserSearchCommand/RoomSearchCommand` `commands.py:548/:569/:593` (return None, no timer, no event, thinner). Both write same `requests[ticket]`.
- `search(q)`: ticket=`next(_ticket_generator)`; `send_server_messages(FileSearch.Request(ticket,query))`; register `requests[ticket]=SearchRequest`; if `request_timeout>0` start Timer→`_timeout_search_request`; emit `SearchRequestSentEvent`; return request. (default timeout=0 ⇒ NO auto-cleanup.)
- `SearchRequest` `model.py:97` (mutable, slots): ticket, query, search_type(NETWORK/USER/ROOM/WISHLIST), room?, username?, results:list[SearchResult] (filled in-place, only if `store_results` True), started, timer?.
- Results via `_on_peer_search_reply` `:380`: build `SearchResult`, `requests[ticket]` lookup (KeyError→warn+drop = how removed/timed-out requests ignore late replies), append if store_results, emit `SearchResultEvent(query,result)`, disconnect conn.
- `SearchResult` `model.py:83`: ticket, username(download key), has_free_slots, avg_speed(bytes/s, PRIMARY rank), queue_size, shared_items:list[FileData], locked_results:list[FileData] (coalesced []).
- **Collection patterns** (no end-of-results msg): (a) push — register async listener for SearchResultEvent; (b) poll — `await asyncio.sleep(window)` (15-30s typical) then read `request.results`.
- Lifecycle exit 3 ways: `remove_request(req|ticket)` `:104` = `requests.pop` (NO event, NO timer-cancel, raises KeyError if gone); timeout = `del`+`SearchRequestRemovedEvent`; never (default) → grows forever, CALL remove_request to bound memory. ⚠ remove_request emits no event; don't rely on SearchRequestRemovedEvent for manual removal.
- Ranking is YOUR job (lib doesn't sort/dedup). Signals: has_free_slots, avg_speed, queue_size, per-file get_attribute_map(). FileData.filename = full remote path, sep may be `\` (Windows peers) → split both `\` and `/` for basename.

## TRANSFERS  (`transfer/{manager,model,state,cache}.py`)
- **Identity = tuple (remote_path, username, direction)** `model.py:370` — NO stable id; lookups build throwaway Transfer + scan. Cache key = SHA-256 of those 3 `cache.py:62`.
- `Transfer` `model.py:65` (plain obj, 3 required args). Key fields: username/remote_path/direction(UPLOAD=0/DOWNLOAD=1) identity; local_path(nulled by reset_local_vars); state(TransferState OBJ not enum, starts VirginState); **bytes_transfered (ONE 'r')** `:101` (`bytes_transferred` is alias property); filesize; fail_reason/abort_reason; remotely_queued(dl only); place_in_queue; start_time/complete_time (`set_complete_time` only records if start_time set); _speed_log(deque maxlen 30 @0.1s); _state_lock; _transfer_task/_remotely_queue_task.
- **speed is computed** not stored: `get_speed()` 0 if never started; live = sum bytes over window; finished = bytes/(complete-start) `model.py:239`.
- State concurrency: every public TransferState method wrapped by `_wrap_lock()` → acquires `transfer._state_lock` `state.py:140`; transitions mutually exclusive per-transfer; each returns bool (legal?).
- States enum `state.py:56` (no value 2): UNSET=-1,VIRGIN=0,QUEUED=1,INITIALIZING=3,INCOMPLETE=4,DOWNLOADING=5,UPLOADING=6,COMPLETE=7,FAILED=8,ABORTED=9,PAUSED=10. Verbs: queue/initialize/start_transferring/complete/incomplete/fail/abort/pause (default→warn+False). `Transfer.transition` swaps state + notifies listeners → manager requests mgmt cycle.
- Legal transitions: VIRGIN→queue/pause; QUEUED→initialize/fail/abort(del file)/pause; INITIALIZING→start_transferring(set start, reset_queue_vars)/queue/fail/abort(del)/pause; DOWNLOADING→complete/incomplete/fail/abort(del)/pause(keep file); UPLOADING→complete/fail/abort(KEEP file)/pause (NO incomplete); INCOMPLETE→queue/initialize(reset time only, keep bytes)/fail/abort(del)/pause; COMPLETE→queue ONLY (dl: reset_progress+reset_local = fresh redownload); FAILED→queue ONLY (clears fail+abort reason, keeps partial for resume); PAUSED→queue/abort(del)/fail; ABORTED→queue ONLY (dl resets progress+local).
- `reset_*_vars`: reset_local(local_path=None, filesize=None); reset_progress(bytes_transfered=0, _offset=0); reset_queue(place_in_queue=None, remotely_queued=False, attempt counters); reset_time(start/complete=None, clear speed log). `_remove_local_file` `state.py:27` returns early for uploads; else os.remove + local_path=None. Pause NEVER deletes.
- Predicates: is_finalized=COMPLETE/ABORTED/FAILED; is_processing=DOWNLOADING/UPLOADING/INITIALIZING; is_transferring=DOWNLOADING/UPLOADING; is_transfered = `filesize==bytes_transfered`.
- **Download handshake**: (1) remote-queue `PeerTransferQueue(filename)` 0x2B → remotely_queued=True; (2) uploader `PeerTransferRequest(direction=DOWNLOAD,ticket,filename,filesize)` 0x28 → `_on_peer_transfer_request`→state.initialize, set filesize; (3) reply `PeerTransferReply(ticket,allowed=True)` 0x29; (4) register `_file_connection_futures[ticket]`, await ≤60s; (5) uploader opens NEW 'F' conn, sends uint32 ticket → `_on_peer_initialized` resolves future; (6) offset=getsize(local_path), bytes_transfered=offset, send uint64 offset; (7) raw bytes, receive_file appends 'ab'; (8) is_transfered→complete else fail(CANCELLED), disconnect. `_initialize_download` `manager.py:765`; `_download_file` `:1070` (OSError→FAILED FILE_READ_ERROR; ConnectionReadError→INCOMPLETE retryable; Cancelled→re-raise).
- Peer transfer msgs (all .Request): PeerTransferRequest 0x28 (direction:uint32,ticket:uint32,filename:string,filesize:uint64 opt); PeerTransferReply 0x29 (ticket,allowed:boolean,filesize if_true allowed,reason if_false allowed); PeerTransferQueue 0x2B; PeerPlaceInQueueReply 0x2C (filename,place:uint32); PeerUploadFailed 0x2E; PeerTransferQueueFailed 0x32 (filename,reason); PeerPlaceInQueueRequest 0x33. ticket/offset on 'F' conn are RAW primitives, not framed.
- **Public API** (`transfers.*`, all verify membership→`TransferNotFoundError`, illegal transition→`InvalidStateTransition`): `download(username,filename,paused=False)` `manager.py:226` = add()+state.queue()/pause() (RETURNS existing if matched); `queue(t)` `:273`; `pause(t)` `:305` (keep file); `abort(t)` `:251` (del partial dl / keep upload); `remove(t)` `:346` (abort then drop+TransferRemovedEvent); `add(t)` `:319` (register only, does NOT start, +TransferAddedEvent); `find_transfer`/`get_transfer`(raising); `request_place_in_queue(t)` `:730` (15s timeout). Read helpers: get_downloads/uploads, get_downloading/uploading, get_free_upload_slots=`upload_slots-len(uploading)` floored 0, get_download_speed/upload_speed, get_place_in_queue.
- **Mgmt loop** `manager.py:517` self-pacing 0.05-0.25s, coalesced via maxsize=1 queue; runs manage_user_tracking + manage_transfers each cycle. `_get_queued_transfers` `:596` skips OFFLINE users; download eligible if QUEUED or INCOMPLETE (auto-resume) or (FAILED & fail_reason is None — reason-LESS only). Auto-retry triggers: read-error→INCOMPLETE, reason-less FAILED, PeerUploadFailed clears remotely_queued, cache-loader→INCOMPLETE on startup. Uploads: 1 queued/user, ranked `_prioritize_uploads` +1 online/away, +5 friend, +100 privileged.
- **Progress** `report_interval` 0.250s: walk transfers, diff frozen `TransferProgressSnapshot`(state,bytes_transfered,speed,start_time,complete_time,fail_reason,abort_reason), emit one `TransferProgressEvent(updates=list[(Transfer,prev,cur)])` if any changed. Idle transfers emit nothing.
- **Cache/resume** `cache.py`: Protocol read()/write(). `TransferNullCache` default (no resume). `TransferShelveCache(data_directory=)` persists via shelve. `__getstate__` drops runtime fields, stores state as enum value; `__setstate__` rebuilds via `init_from_state`, fresh lock/log/snapshot. Startup `read_cache` `manager.py:147`: clear remotely_queued; INITIALIZING→queue; is_transferring→COMPLETE if is_transfered else INCOMPLETE + reset_time. Resume works because local_path & bytes_transfered untouched → `_calculate_offset`=getsize, reopen 'ab', request `filesize-bytes_transfered`.
- **NO content checksum** anywhere — completion = byte count only. (only md5 in codebase = login password hash.)

## GOTCHAS (master)
1. Listeners weakref'd → bare lambda/closure/unretained-bound-method GC'd, silently stops firing. Keep strong ref. `events.py:130-136,211`
2. `download()` queues immediately (add+queue same coroutine) → races mgmt loop before you set local_path → falls back to `shares.download`. Use add()→set local_path→queue(). `manager.py:237-247`
3. local_path nulled on re-queue of COMPLETE/ABORTED download (reset_local_vars) → re-assign AFTER queue(). `state.py:305/391`
4. local_path nulled + file DELETED on abort()/remove() of a download (uploads keep file). `state.py:27-39`
5. No stable transfer id — identity=(remote_path,username,direction). `model.py:370`
6. No file checksum — is_transfered = `filesize==bytes_transfered` only.
7. Leech-only: `upnp.enabled=False` + `shares.scan_on_start=False`.
8. Searches never complete — collect over window then remove_request. `manager.py:380-401`
9. Peer browse can hang forever — use execute(timeout=) + catch asyncio.TimeoutError. `commands.py:928`
10. No .env — construct Settings in code.
11. login() Login.Response read synchronously, bypasses dispatch — server events only after SessionInitializedEvent.
12. SharedDirectoryChangeEvent uses emit_sync → async listeners dropped.

## FORK DIVERGENCES (vs upstream v1.6.3) — 6 LOG DOWNGRADES, zero logic change
1. `network.py:1179` ConnectToPeer fulfil failure: warn→debug (NAT'd leech can't fulfil callbacks).
2. `distributed.py:604` "not registered with distributed network": warn→debug (conns close pre-init, esp NAT).
3. `connection.py:307` reader-loop read error: warn→debug (peers dropping mid-read is normal).
4. `connection.py:140` & `:274` disconnect exception: warn→debug (peer resets expected; also `:487` send-on-closing).
5. `connection.py:312` failed to deserialize: warn→debug (per-conn garbage).
6. `client.py:221` loop exception handler: error+traceback→debug-no-traceback for NetworkError/ConnectionError/TimeoutError/CancelledError (genuinely unexpected still full traceback `:223`).
⇒ **When diagnosing connectivity, raise log handler to DEBUG**; quiet WARNING stream ≠ nothing failed.

## RECIPES (minimal)
```python
# 1. construct + login
from aioslsk.client import SoulSeekClient
from aioslsk.settings import Settings, CredentialsSettings
s = Settings(credentials=CredentialsSettings(username="u", password="p"))
s.network.upnp.enabled = False; s.shares.scan_on_start = False
s.shares.download = "/tmp/dl"
client = SoulSeekClient(s); await client.start(); await client.login()   # AuthenticationError on bad creds
# async-with = start/stop only (NOT login). run_until_stopped() blocks until stop().

# 2. search + collection window + rank
req = await client.searches.search(query)        # returns SearchRequest; results stream async
await asyncio.sleep(window)                        # 15-30s
cands = [(r, fd, fd.get_attribute_map().get(AttributeKey.BITRATE, 0))
         for r in req.results for fd in r.shared_items]
cands.sort(key=lambda c: (c[0].has_free_slots, c[0].avg_speed, c[2], c[1].filesize), reverse=True)
client.searches.remove_request(req)                # drop late replies, bound memory

# 3. browse peer folder (can hang → timeout)
from aioslsk.commands import PeerGetDirectoryContentCommand
try:
    dirs = await client.execute(PeerGetDirectoryContentCommand(username, directory),
                                response=True, timeout=15)   # list[DirectoryData]
except asyncio.TimeoutError: dirs = []

# 4. download to EXACT path WITHOUT race
from aioslsk.transfer.model import Transfer, TransferDirection
t = await client.transfers.add(Transfer(username, remote_path, TransferDirection.DOWNLOAD))  # add does NOT start
t.local_path = local_path                          # set BEFORE queue
await client.transfers.queue(t)                    # now eligible
# re-queue a finished/aborted dl nulls local_path → re-set AFTER queue()

# 5. listeners — MUST keep strong ref (else GC'd)
class W:
    def __init__(self, c):
        self._c = c
        c.events.register(TransferProgressEvent, self.on_p)   # bound method, self retained
    async def on_p(self, e):
        for t, prev, cur in e.updates: ...
w = W(client)   # hold this
```
