"""Local rendezvous-server stand-in (W2-H13, D220 b): protocol v2 of connectionUDP/rendezvous_client.cpp (oracle:
rendezvous_server.cpp) on 127.0.0.1 ephemeral TCP + UDP; crypto = the game's libsodium.dll via ctypes; fresh keys per run;
every frame and event in events() (+ log_path JSON lines). `python rendezvous_stub.py --selftest [--dll-dir DIR]` -> exit 0."""
# flake8: noqa: E401,E701,E702,E731
import base64, ctypes, hashlib, hmac, json, os, socket, struct, sys, threading, time

VERSION, MAX_FRAME = 2, 64 * 1024
canon = lambda obj: json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)  # = jsoncpp compact writer
b64e = lambda raw: base64.b64encode(raw).decode("ascii")
b64d = lambda text: base64.b64decode(str(text).encode("ascii"), validate=True)
frame_of = lambda obj: (lambda raw: struct.pack(">I", len(raw)) + raw)(canon(obj).encode())  # 4-byte BE length + JSON

def close_quiet(s):
    try: s.close()
    except OSError: pass

class Sodium:
    """The few libsodium calls the protocol needs, bound with ctypes."""
    def __init__(self, dll_dir):
        self.lib = lib = ctypes.CDLL(os.path.join(dll_dir, "libsodium.dll"))
        if lib.sodium_init() < 0: raise RuntimeError("sodium_init failed")
        c, u = ctypes.c_char_p, ctypes.c_ulonglong
        lib.crypto_box_keypair.argtypes = lib.crypto_sign_keypair.argtypes = [c, c]
        lib.crypto_box_seal.argtypes, lib.crypto_box_seal_open.argtypes = [c, c, u, c], [c, c, u, c, c]
        lib.crypto_sign_detached.argtypes, lib.crypto_sign_verify_detached.argtypes = [c, ctypes.c_void_p, c, u, c], [c, c, u, c]
    def keypair(self, sign=False):
        pk, sk = ctypes.create_string_buffer(32), ctypes.create_string_buffer(64 if sign else 32)
        (self.lib.crypto_sign_keypair if sign else self.lib.crypto_box_keypair)(pk, sk); return pk.raw, sk.raw
    def seal(self, plain, pk):
        out = ctypes.create_string_buffer(48 + len(plain))
        if self.lib.crypto_box_seal(out, plain, len(plain), pk) != 0: raise RuntimeError("crypto_box_seal failed")
        return out.raw
    def seal_open(self, sealed, pk, sk):
        out = ctypes.create_string_buffer(max(0, len(sealed) - 48))
        return out.raw if len(sealed) >= 48 and self.lib.crypto_box_seal_open(out, sealed, len(sealed), pk, sk) == 0 else None
    def sign(self, msg, sk):
        sig = ctypes.create_string_buffer(64); self.lib.crypto_sign_detached(sig, None, msg, len(msg), sk); return sig.raw
    def verify(self, sig, msg, pk):
        return self.lib.crypto_sign_verify_detached(sig, msg, len(msg), pk) == 0

class RendezvousStub:
    def __init__(self, dll_dir, log_path=None, host="127.0.0.1"):
        self.na = Sodium(dll_dir)
        (self.box_pk, self.box_sk), (self.sign_pk, self.sign_sk) = self.na.keypair(), self.na.keypair(sign=True)
        self.host, self.log_path, self.tcp_port, self.udp_port = host, log_path, 0, 0
        self._lock, self._stop, self._t0 = threading.RLock(), threading.Event(), time.monotonic()
        self._events, self._rooms, self._threads, self._socks, self._seq, self._conn = [], {}, [], set(), 0, 0
    def log(self, ev, **kw):
        rec = dict(t=round(time.monotonic() - self._t0, 3), ev=ev, **kw)
        with self._lock:
            self._events.append(rec)
            if self.log_path:
                with open(self.log_path, "a", encoding="ascii", newline="\n") as f: f.write(canon(rec) + "\n")
        return rec
    def events(self, ev=None):
        with self._lock: return [dict(e) for e in self._events if ev is None or e["ev"] == ev]
    def rooms(self):
        with self._lock:
            return [dict({k: r[k] for k in ("room_id", "seq", "name", "host_name", "listed", "closed", "gone")},
                         session_ready=r["session_key"] is not None, players=[dict({k: p[k] for k in (
                             "name", "player_id", "registered", "peer_ready_sent")}, udp=p["udp_addr"]) for p in r["players"]])
                    for r in sorted(self._rooms.values(), key=lambda r: r["seq"])]
    def wait_room(self, host_name, after=None, timeout=30.0):  # first live room by host_name created after `after`, else None
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                floor = self._rooms[after]["seq"] if after in self._rooms else 0
                hits = sorted((r["seq"], r["room_id"]) for r in self._rooms.values() if r["host_name"] == host_name
                              and not r["gone"] and r["seq"] > floor and r["room_id"] != after)
            if hits or time.monotonic() >= deadline: return hits[0][1] if hits else None
            time.sleep(0.1)
    def write_config(self, path):
        cfg = {"servers": [{"name": "HarnessStub", "host": self.host, "tcpPort": self.tcp_port, "udpPort": self.udp_port,
                            "serverBoxPublicKey": b64e(self.box_pk), "serverSignPublicKey": b64e(self.sign_pk)}]}
        with open(path, "w", encoding="ascii", newline="\n") as f: json.dump(cfg, f, indent=1)
        self.log("config", path=path); return path
    def start(self):
        self._tcp, self._udp = socket.socket(socket.AF_INET, socket.SOCK_STREAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._tcp.bind((self.host, 0)); self._tcp.listen(16); self._udp.bind((self.host, 0))
        self.tcp_port, self.udp_port = self._tcp.getsockname()[1], self._udp.getsockname()[1]
        self._spawn(self._accept_loop); self._spawn(self._udp_loop)
        self.log("start", tcp=self.tcp_port, udp=self.udp_port, box_pk=b64e(self.box_pk), sign_pk=b64e(self.sign_pk))
        return self
    def stop(self):
        if self._stop.is_set(): return
        self._stop.set()
        with self._lock: socks = [self._tcp, self._udp] + list(self._socks)
        for s in socks: close_quiet(s)
        for t in list(self._threads): t.join(timeout=3)
        self.log("stop", threads_alive=sum(t.is_alive() for t in self._threads))
    def _spawn(self, fn, *args):
        t = threading.Thread(target=fn, args=args, daemon=True); t.start(); self._threads.append(t)
    def _accept_loop(self):
        self._tcp.settimeout(0.5)
        while not self._stop.is_set():
            try: s, addr = self._tcp.accept()
            except socket.timeout: continue
            except OSError: break
            s.settimeout(0.5)
            with self._lock: self._conn += 1; cid = self._conn; self._socks.add(s)
            self.log("tcp_accept", conn=cid, src="%s:%d" % addr); self._spawn(self._serve, s, cid)
    def _recv_frame(self, s, buf):
        while not self._stop.is_set():
            n = struct.unpack(">I", bytes(buf[:4]))[0] if len(buf) >= 4 else None
            if n is not None and (n == 0 or n > MAX_FRAME): return None
            if n is not None and len(buf) >= 4 + n:
                frame = bytes(buf[4:4 + n]); del buf[:4 + n]; return frame
            try: chunk = s.recv(65536)
            except socket.timeout: continue
            except OSError: return None
            if not chunk: return None
            buf.extend(chunk)
    def _send(self, cid, s, inner, cpk):  # SERVER_MSG = sealed(inner + server_sig = Ed25519 over compact inner)
        sig = self.na.sign(canon(inner).encode(), self.sign_sk)
        sealed = self.na.seal(canon(dict(inner, server_sig=b64e(sig))).encode(), cpk)
        frame, ok = frame_of({"type": "SERVER_MSG", "version": VERSION, "sealed": b64e(sealed)}), True
        try:
            with self._lock: s.sendall(frame)
        except OSError: ok = False
        self.log("tcp_out", conn=cid, kind=inner["kind"], len=len(frame) - 4, ok=ok, msg=inner); return ok
    def _error(self, cid, s, cpk, message, **kw):
        self.log("ERROR", conn=cid, message=message, **kw); self._send(cid, s, {"kind": "ERROR", "message": message}, cpk)
    def _serve(self, s, cid):
        buf, player, req = bytearray(), None, None
        try:
            frame = self._recv_frame(s, buf)
            if frame is None: return
            try:
                outer = json.loads(frame)
                cpk, plain = b64d(outer["client_box_pk"]), self.na.seal_open(b64d(outer["sealed"]), self.box_pk, self.box_sk)
                if outer.get("type") == "CLIENT_MSG" and len(cpk) == 32 and plain is not None: req = json.loads(plain)
            except (ValueError, KeyError, TypeError, AttributeError): pass
            if not isinstance(req, dict):
                return self.log("bad_frame", conn=cid, len=len(frame), head=frame[:120].decode("ascii", "replace"))
            kind = req.get("kind", "")
            self.log("tcp_in", conn=cid, kind=kind, len=len(frame), req=req)
            handler = {"LIST_ROOMS": self._h_list, "CREATE_ROOM": self._h_create,
                       "JOIN_ROOM": self._h_join, "CLOSE_ROOM": self._h_close}.get(kind)
            if handler is None: return self._error(cid, s, cpk, "unknown request kind")
            player = handler(cid, s, cpk, req)
            while player is not None:  # CREATE/JOIN keep the control socket open until the game closes it
                extra = self._recv_frame(s, buf)
                if extra is None: break
                self.log("tcp_in_ignored", conn=cid, len=len(extra))
        finally:
            self._closed(s, cid, player)
    def _closed(self, s, cid, player):  # socket closed: drop the player if the room has no session key yet
        dropped = gone = False
        with self._lock:
            self._socks.discard(s)
            room = self._rooms.get(player["room"]) if player else None
            if room is not None and room["session_key"] is None and any(p is player for p in room["players"]):
                room["players"] = [p for p in room["players"] if p is not player]
                dropped, gone = True, not room["players"]; room["gone"] = gone
        close_quiet(s)
        self.log("socket_closed", conn=cid, player=player and player["name"], dropped=dropped, room_gone=gone)
    def _player(self, cid, s, cpk, req, rid, pid):
        return dict(name=(req.get("player_name") or "Player")[:32], player_id=pid, room=rid, conn=cid, sock=s,
                    cpk=cpk, udp_token=os.urandom(32), udp_addr=None, registered=False, peer_ready_sent=False)
    def _accept(self, cid, s, cpk, room, player, kind, host_token=None):
        ok = dict({"kind": kind, "room_id": room["room_id"], "session_id": room["session_id"], "player_id": player["player_id"],
                   "desired_players": room["desired"], "udp_token": b64e(player["udp_token"])}, **({"host_token": host_token} if host_token else {}))
        self._send(cid, s, ok, cpk); self._send(cid, s, {"kind": "WAITING", "message": "waiting for peer UDP registration"}, cpk)
    def _h_list(self, cid, s, cpk, req):
        gv, mh, compat = req.get("game_version", ""), req.get("mod_hash", ""), bool(req.get("compatible_only"))
        with self._lock:
            rooms = [dict({k: r[k] for k in ("room_id", "name", "host_name", "region", "password_required", "is_campaign", "game_version",
                          "mod_hash")}, players=len(r["players"]), max_players=r["desired"], locked=False, created_at_ms=r["created_ms"])
                     for r in sorted(self._rooms.values(), key=lambda r: r["seq"])
                     if r["listed"] and not (r["gone"] or r["closed"] or r["session_key"]) and len(r["players"]) < r["desired"]
                     and not (compat and ((gv and r["game_version"] != gv) or (mh and r["mod_hash"] != mh)))]
        self.log("LIST_ROOMS", conn=cid, returned=[r["room_id"] for r in rooms])
        self._send(cid, s, {"kind": "ROOM_LIST", "rooms": rooms}, cpk)
    def _h_create(self, cid, s, cpk, req):
        token, g = b64e(os.urandom(32)), req.get
        with self._lock:
            self._seq += 1; rid = b64e(os.urandom(9)).replace("+", "A").replace("/", "B")
            room = dict(room_id=rid, seq=self._seq, name=(g("room_name") or "Game")[:48], host_name=(g("player_name") or "Host")[:32],
                        region=str(g("region", ""))[:32], password=g("password", ""), listed=bool(g("listed", True)),
                        password_required=bool(g("password_required", bool(g("password")))), is_campaign=bool(g("is_campaign")),
                        game_version=g("game_version", ""), mod_hash=g("mod_hash", ""), session_key=None, host_token=token,
                        desired=max(2, min(4, int(g("desired_players", 2)))), closed=False, gone=False, players=[],
                        session_id=str(int.from_bytes(os.urandom(8), "little") or 1), created_ms=str(int(time.time() * 1000)))
            player = self._player(cid, s, cpk, req, rid, 1)
            room["players"].append(player); self._rooms[rid] = room
        self.log("CREATE_ROOM", conn=cid, room=rid, seq=room["seq"], host=room["host_name"], listed=room["listed"])
        self._accept(cid, s, cpk, room, player, "CREATE_ROOM_OK", token); return player
    def _h_join(self, cid, s, cpk, req):
        rid, gv, mh = req.get("room_id") or req.get("room") or "", req.get("game_version", ""), req.get("mod_hash", "")
        with self._lock:
            room, player = self._rooms.get(rid), None
            err = ("room id missing" if not rid else "room not found" if room is None or room["gone"]
                   else "room locked" if room["closed"] or room["session_key"] is not None
                   else "room full" if len(room["players"]) >= room["desired"]
                   else "wrong room password" if room["password_required"] and req.get("password", "") != room["password"]
                   else "incompatible mods" if (gv and room["game_version"] and gv != room["game_version"])
                   or (mh and room["mod_hash"] and mh != room["mod_hash"]) else None)
            if err is None:
                player = self._player(cid, s, cpk, req, rid, len(room["players"]) + 1); room["players"].append(player)
        if err: return self._error(cid, s, cpk, err, room=rid)
        self.log("JOIN_ROOM", conn=cid, room=rid, player=player["name"], player_id=player["player_id"])
        self._accept(cid, s, cpk, room, player, "JOIN_ROOM_OK"); return player
    def _h_close(self, cid, s, cpk, req):
        rid, token = req.get("room_id", ""), req.get("host_token", "")
        with self._lock:
            room = self._rooms.get(rid)
            err = ("room id or host token missing" if not rid or not token else "room not found"
                   if room is None or room["gone"] else "bad host token" if token != room["host_token"] else None)
            if err is None: room["closed"], room["listed"] = True, False
        if err: return self._error(cid, s, cpk, err, room=rid)
        self.log("CLOSE_ROOM", conn=cid, room=rid); self._send(cid, s, {"kind": "CLOSE_ROOM_OK"}, cpk)
    def _udp_loop(self):
        self._udp.settimeout(0.5)
        while not self._stop.is_set():
            try: data, addr = self._udp.recvfrom(2048)
            except (socket.timeout, ConnectionResetError): continue
            except OSError: break
            self._on_udp(data, addr)
    def _on_udp(self, data, addr):
        src, msg = "%s:%d" % addr, None
        try: msg = json.loads(data)
        except ValueError: pass
        if not isinstance(msg, dict) or msg.get("type") != "UDP_REGISTER": return self.log("udp_ignored", src=src, len=len(data))
        rid, pid, first = str(msg.get("room", "")), msg.get("player_id", 0), False
        with self._lock:
            room = self._rooms.get(rid)
            player = next((p for p in room["players"] if p["player_id"] == pid), None) if room else None
            verdict = ("unknown-room" if room is None or room["gone"] else "closed-room" if room["closed"]
                       else "unknown-player" if player is None else "ok" if self._mac_ok(msg, player) else "bad-mac")
            if verdict == "ok": first, player["udp_addr"], player["registered"] = not player["registered"], addr, True
        self.log("UDP_REGISTER", room=rid, player_id=pid, src=src, hmac=verdict, first=first)
        if verdict == "ok": self._maybe_ready(room)
    def _mac_ok(self, msg, player):  # mac = HMAC-SHA256(udp_token, compact JSON without mac)
        mac_data = {"type": "UDP_REGISTER", "version": VERSION, "room": str(msg.get("room", "")),
                    "player_id": msg.get("player_id", 0), "nonce": str(msg.get("nonce", ""))}
        try: mac = b64d(msg.get("mac", ""))
        except ValueError: return False
        return hmac.compare_digest(hmac.new(player["udp_token"], canon(mac_data).encode(), hashlib.sha256).digest(), mac)
    def _maybe_ready(self, room):
        with self._lock:
            ps = room["players"]
            if len(ps) != 2 or len(ps) < room["desired"] or not all(p["registered"] for p in ps): return
            if room["session_key"] is None: room["session_key"] = os.urandom(32)
            key_sha = hashlib.sha256(room["session_key"]).hexdigest()[:16]
            for me, peer in ((ps[0], ps[1]), (ps[1], ps[0])):
                if me["peer_ready_sent"]: continue
                inner = {"kind": "PEER_READY", "session_id": room["session_id"], "session_key": b64e(room["session_key"]),
                         "remote_host": peer["udp_addr"][0], "remote_port": peer["udp_addr"][1],
                         "remote_player_id": peer["player_id"], "peer_player_name": peer["name"]}
                me["peer_ready_sent"] = self._send(me["conn"], me["sock"], inner, me["cpk"])
                self.log("PEER_READY", room=room["room_id"], to=me["name"], to_player_id=me["player_id"],
                         remote="%s:%d" % peer["udp_addr"], key_sha=key_sha, sent=me["peer_ready_sent"])

def _selftest(dll_dir):  # CREATE + JOIN + 2 UDP_REGISTER -> 2 PEER_READY with one key; ERROR; CLOSE; LIST
    stub = RendezvousStub(dll_dir).start(); na, fails = stub.na, []
    def check(name, cond, detail=""):
        print("%-50s %s %s" % (name, "PASS" if cond else "FAIL", detail)); fails.extend([] if cond else [name])
    def ask(kind, **payload):  # a fresh connection carrying one sealed CLIENT_MSG
        (pk, sk), s = na.keypair(), socket.create_connection((stub.host, stub.tcp_port), 5)
        conn = dict(pk=pk, sk=sk, s=s, buf=bytearray())
        sealed = na.seal(canon(dict(payload, kind=kind, version=VERSION)).encode(), stub.box_pk)
        conn["s"].sendall(frame_of({"type": "CLIENT_MSG", "version": VERSION, "client_box_pk": b64e(pk), "sealed": b64e(sealed)}))
        return conn
    def recv(conn):  # one SERVER_MSG, opened and signature-checked the way the game does it
        buf = conn["buf"]
        while len(buf) < 4 or len(buf) < 4 + struct.unpack(">I", bytes(buf[:4]))[0]:
            chunk = conn["s"].recv(65536)  # the 5 s socket timeout raises: no silent hang
            if not chunk: raise ConnectionError("stub closed the connection")
            buf.extend(chunk)
        n = struct.unpack(">I", bytes(buf[:4]))[0]; frame = bytes(buf[4:4 + n]); del buf[:4 + n]
        inner = json.loads(na.seal_open(b64d(json.loads(frame)["sealed"]), conn["pk"], conn["sk"])); sig = b64d(inner.pop("server_sig"))
        check("  signature verifies (%s)" % inner.get("kind"), na.verify(sig, canon(inner).encode(), stub.sign_pk))
        return inner
    def register(sock, rid, pid, token, good=True):
        d = {"type": "UDP_REGISTER", "version": VERSION, "room": rid, "player_id": pid, "nonce": b64e(os.urandom(24))}
        mac = hmac.new(b64d(token) if good else os.urandom(32), canon(d).encode(), hashlib.sha256).digest()
        sock.sendto(canon(dict(d, mac=b64e(mac))).encode(), (stub.host, stub.udp_port))
    try:
        host = ask("CREATE_ROOM", room_name="Self", player_name="SelfHost", password="", listed=True, region="",
                   password_required=False, is_campaign=False, game_version="v", mod_hash="m", desired_players=2)
        ok1, w1 = recv(host), recv(host); rid = ok1.get("room_id")
        check("CREATE -> CREATE_ROOM_OK player 1 + WAITING", ok1["kind"] == "CREATE_ROOM_OK" and ok1["player_id"] == 1
              and w1["kind"] == "WAITING" and int(ok1["session_id"]) != 0, rid)
        check("LIST -> ROOM_LIST holds the room", [r["room_id"] for r in recv(ask(
            "LIST_ROOMS", game_version="v", mod_hash="m", compatible_only=True))["rooms"]] == [rid])
        check("wait_room(SelfHost) == room", stub.wait_room("SelfHost", timeout=2) == rid)
        err = recv(ask("JOIN_ROOM", room_id="nope", player_name="X"))
        check("JOIN unknown room -> ERROR room not found", err == {"kind": "ERROR", "message": "room not found"})
        cli = ask("JOIN_ROOM", room_id=rid, player_name="SelfClient", password="", game_version="v", mod_hash="m")
        ok2, w2 = recv(cli), recv(cli)
        check("JOIN -> JOIN_ROOM_OK player 2 + WAITING", ok2["kind"] == "JOIN_ROOM_OK" and ok2["player_id"] == 2
              and w2["kind"] == "WAITING" and ok2["session_id"] == ok1["session_id"])
        hu, cu = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        hu.bind((stub.host, 0)); cu.bind((stub.host, 0))
        register(cu, rid, 2, ok2["udp_token"], good=False); register(hu, rid, 1, ok1["udp_token"]); register(cu, rid, 2, ok2["udp_token"])
        pr1, pr2 = recv(host), recv(cli)
        check("2 UDP_REGISTER -> 2 PEER_READY", pr1["kind"] == pr2["kind"] == "PEER_READY")
        check("one session key; ids and names cross", pr1["session_key"] == pr2["session_key"]
              and pr1["session_id"] == ok1["session_id"] and pr1["remote_player_id"] == 2 and pr2["remote_player_id"] == 1
              and pr1["peer_player_name"] == "SelfClient" and pr2["peer_player_name"] == "SelfHost"
              and len(b64d(pr1["session_key"])) == 32)
        check("remote endpoints = the peers' UDP sources", pr1["remote_port"] == cu.getsockname()[1]
              and pr2["remote_port"] == hu.getsockname()[1] and pr1["remote_host"] == "127.0.0.1")
        check("JOIN after PEER_READY -> ERROR room locked", recv(ask("JOIN_ROOM", room_id=rid, player_name="Late"))
              == {"kind": "ERROR", "message": "room locked"})
        check("CLOSE bad token -> ERROR bad host token", recv(ask("CLOSE_ROOM", room_id=rid, host_token="x"))
              == {"kind": "ERROR", "message": "bad host token"})
        check("CLOSE -> CLOSE_ROOM_OK", recv(ask("CLOSE_ROOM", room_id=rid, host_token=ok1["host_token"])) == {"kind": "CLOSE_ROOM_OK"})
        check("LIST after CLOSE is empty", recv(ask("LIST_ROOMS", game_version="", mod_hash="", compatible_only=False))["rooms"] == [])
        check("wait_room(after=room) times out to None", stub.wait_room("SelfHost", after=rid, timeout=0.5) is None)
        [s.close() for s in (host["s"], cli["s"], hu, cu)]; time.sleep(1.0)
        verdicts, r0 = [e["hmac"] for e in stub.events("UDP_REGISTER")], stub.rooms()[0]
        check("HMAC verdicts: bad-mac, ok, ok", verdicts == ["bad-mac", "ok", "ok"], verdicts)
        check("room kept after its sockets close (session key)", r0["session_ready"] and not r0["gone"])
    except Exception as exc:  # a selftest reports any failure
        check("selftest raised", False, repr(exc))
    finally:
        stub.stop()
    for e in stub.events(): print("  EVENT " + canon({k: v for k, v in e.items() if k not in ("msg", "req")}))
    print("SELFTEST %s (%d events, %d failures)" % ("PASS" if not fails else "FAIL", len(stub.events()), len(fails)))
    return 0 if not fails else 1

if __name__ == "__main__":
    if "--selftest" not in sys.argv: sys.exit(print(__doc__))
    sys.exit(_selftest(sys.argv[sys.argv.index("--dll-dir") + 1] if "--dll-dir" in sys.argv
                       else os.path.dirname(os.environ["OXC_TEST_EXE"]) if os.environ.get("OXC_TEST_EXE")
                       else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bin", "x64", "Release")))
