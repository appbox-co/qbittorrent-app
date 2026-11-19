#!/usr/bin/env python3
"""Unit tests for /defaults/qbtcheck, the no-public-seeding check.

Runs without qBittorrent: the client is a fake. If the qbittorrentapi package
is missing (outside the image) a stub module stands in for the import.

Usage: tests/test-qbtcheck.py
       QBTCHECK_PATH=/defaults/qbtcheck python3 test-qbtcheck.py   (in the image)
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

SCRIPT = os.environ.get("QBTCHECK_PATH") or str(
    Path(__file__).resolve().parent.parent / "root" / "defaults" / "qbtcheck")

try:
    import qbittorrentapi  # noqa: F401
except ImportError:
    sys.modules["qbittorrentapi"] = types.ModuleType("qbittorrentapi")

loader = importlib.machinery.SourceFileLoader("qbtcheck", SCRIPT)
spec = importlib.util.spec_from_loader("qbtcheck", loader)
qbtcheck = importlib.util.module_from_spec(spec)
loader.exec_module(qbtcheck)

KEY = "0123456789abcdef0123456789abcdef"
C411_URLS = [
    "https://c411.org/announce/" + KEY,
    "https://tk.c411.tw/announce/" + KEY,
]
FRENCH_PRIVATE_MSG = "Ce torrent est privé"


def sticky_trackers(msg):
    """The DHT, PeX and LSD rows qBittorrent adds to every tracker list."""
    return [{"url": "** [%s] **" % name, "msg": msg} for name in ("DHT", "PeX", "LSD")]


class State:
    def __init__(self, complete=True, paused=False, checking=False, errored=False):
        self.is_complete = complete
        self.is_paused = paused
        self.is_checking = checking
        self.is_errored = errored


class Torrent(dict):
    """Stands in for qbittorrentapi's TorrentDictionary (a dict with attributes)."""

    def __init__(self, hash_, name, state=None, **fields):
        super().__init__(hash=hash_, name=name, **fields)
        self.hash = hash_
        self.name = name
        self.state_enum = state or State()


class FakeClient:
    def __init__(self, torrents, trackers=None, properties=None):
        self._torrents = torrents
        self._trackers = trackers or {}
        self._properties = properties or {}
        self.paused = []
        self.tracker_calls = []
        self.property_calls = []
        self.torrents = types.SimpleNamespace(pause=self._pause)

    def _pause(self, torrent_hashes):
        self.paused.append(torrent_hashes)

    def torrents_info(self):
        return self._torrents

    def torrents_trackers(self, torrent_hash):
        self.tracker_calls.append(torrent_hash)
        return self._trackers.get(torrent_hash, [])

    def torrents_properties(self, torrent_hash):
        self.property_calls.append(torrent_hash)
        value = self._properties.get(torrent_hash)
        if isinstance(value, Exception):
            raise value
        return value if value is not None else {}


class TrackerFallbackWeaknesses(unittest.TestCase):
    """Why the original check paused private torrents."""

    def test_announce_passkey_urls_match_neither_pattern(self):
        for url in C411_URLS:
            self.assertFalse(qbtcheck.is_private(url), url)

    def test_translated_private_message_is_not_recognised(self):
        trackers = sticky_trackers(FRENCH_PRIVATE_MSG) + [{"url": C411_URLS[0], "msg": ""}]
        self.assertFalse(qbtcheck.tracker_says_private(trackers))

    def test_existing_patterns_still_match(self):
        self.assertTrue(qbtcheck.is_private("https://tracker.example.org/announce.php?passkey=" + KEY))
        self.assertTrue(qbtcheck.is_private("https://tracker.example.org/" + KEY + "/announce"))
        self.assertTrue(qbtcheck.tracker_says_private(sticky_trackers("This torrent is private")))
        self.assertFalse(qbtcheck.is_private("udp://tracker.opentrackr.org:1337/announce"))


class PrivateFlag(unittest.TestCase):
    def test_info_flag(self):
        self.assertIs(qbtcheck.private_flag({"private": True}), True)
        self.assertIs(qbtcheck.private_flag({"private": False}), False)

    def test_unreadable_info_flag(self):
        self.assertIsNone(qbtcheck.private_flag({}))
        self.assertIsNone(qbtcheck.private_flag({"private": None}))
        self.assertIsNone(qbtcheck.private_flag({"private": 1}))
        self.assertIsNone(qbtcheck.private_flag({"private": "true"}))

    def test_properties_fallback(self):
        self.assertIs(qbtcheck.private_flag({}, {"private": True, "is_private": True}), True)
        self.assertIs(qbtcheck.private_flag({}, {"private": False, "is_private": False}), False)
        # Older WebAPI without "private": use "is_private".
        self.assertIs(qbtcheck.private_flag({}, {"is_private": True}), True)
        self.assertIs(qbtcheck.private_flag({}, {"is_private": False}), False)

    def test_properties_without_metadata(self):
        # "private" is null before metadata; "is_private" then reads false.
        self.assertIsNone(qbtcheck.private_flag({}, {"private": None, "is_private": False}))
        self.assertIsNone(qbtcheck.private_flag({}, {}))

    def test_info_flag_wins_over_properties(self):
        self.assertIs(qbtcheck.private_flag({"private": True}, {"private": False}), True)


class ShouldPause(unittest.TestCase):
    def test_private_flag_keeps_seeding_in_any_language(self):
        for url in C411_URLS:
            trackers = sticky_trackers(FRENCH_PRIVATE_MSG) + [{"url": url, "msg": ""}]
            self.assertEqual(qbtcheck.should_pause(True, trackers), (False, "private torrent"))

    def test_unreadable_flag_never_pauses(self):
        trackers = sticky_trackers("") + [{"url": "udp://tracker.opentrackr.org:1337/announce", "msg": ""}]
        pause, _ = qbtcheck.should_pause(None, trackers)
        self.assertFalse(pause)

    def test_public_torrent_is_paused(self):
        trackers = sticky_trackers("") + [{"url": "udp://tracker.opentrackr.org:1337/announce", "msg": ""}]
        self.assertEqual(qbtcheck.should_pause(False, trackers), (True, "public"))
        self.assertEqual(qbtcheck.should_pause(False, []), (True, "public"))

    def test_tracker_fallback_still_applies_to_unflagged_torrents(self):
        for trackers in (
            sticky_trackers("This torrent is private"),
            [{"url": "https://tracker.example.org/announce.php?passkey=" + KEY, "msg": ""}],
            [{"url": "https://tracker.example.org/" + KEY + "/announce", "msg": ""}],
        ):
            self.assertEqual(qbtcheck.should_pause(False, trackers), (False, "private tracker"))

    def test_unflagged_torrent_on_announce_passkey_url_is_public(self):
        # Without the private flag, DHT and PeX are on: the torrent is public.
        trackers = sticky_trackers("") + [{"url": C411_URLS[0], "msg": ""}]
        self.assertEqual(qbtcheck.should_pause(False, trackers), (True, "public"))


class CheckTorrents(unittest.TestCase):
    def run_check(self, client):
        devnull = open(os.devnull, "w")
        self.addCleanup(devnull.close)
        stdout, sys.stdout = sys.stdout, devnull
        try:
            qbtcheck.check_torrents(client)
        finally:
            sys.stdout = stdout

    def test_french_c411_private_torrent_seeds_public_is_paused(self):
        private = Torrent("a" * 40, "c411-private", private=True)
        public = Torrent("b" * 40, "public", private=False)
        client = FakeClient([private, public], trackers={
            private.hash: sticky_trackers(FRENCH_PRIVATE_MSG) + [{"url": C411_URLS[1], "msg": ""}],
            public.hash: sticky_trackers("") + [{"url": "udp://tracker.opentrackr.org:1337/announce", "msg": ""}],
        })
        self.run_check(client)
        self.assertEqual(client.paused, [public.hash])
        # Trackers are only read for the torrent qBittorrent reports as public.
        self.assertEqual(client.tracker_calls, [public.hash])
        self.assertEqual(client.property_calls, [])

    def test_inactive_and_incomplete_torrents_are_skipped(self):
        torrents = [
            Torrent("c" * 40, "stopped", State(paused=True), private=False),
            Torrent("d" * 40, "checking", State(checking=True), private=False),
            Torrent("e" * 40, "errored", State(errored=True), private=False),
            Torrent("f" * 40, "downloading", State(complete=False), private=False),
        ]
        client = FakeClient(torrents)
        self.run_check(client)
        self.assertEqual(client.paused, [])
        self.assertEqual(client.tracker_calls, [])

    def test_missing_info_flag_falls_back_to_properties(self):
        private = Torrent("1" * 40, "private-old-api")
        public = Torrent("2" * 40, "public-old-api")
        client = FakeClient([private, public], properties={
            private.hash: {"is_private": True},
            public.hash: {"is_private": False},
        })
        self.run_check(client)
        self.assertEqual(client.property_calls, [private.hash, public.hash])
        self.assertEqual(client.paused, [public.hash])

    def test_unreadable_flag_is_not_paused(self):
        failing = Torrent("3" * 40, "properties-error")
        unknown = Torrent("4" * 40, "properties-null", private=None)
        client = FakeClient([failing, unknown], properties={
            failing.hash: RuntimeError("connection reset"),
            unknown.hash: {"private": None, "is_private": False},
        })
        self.run_check(client)
        self.assertEqual(client.paused, [])
        self.assertEqual(client.tracker_calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
