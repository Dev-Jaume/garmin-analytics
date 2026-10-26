"""FIT binari sintètic, sense cap dada personal ni dependència d'un encoder extern."""

import socket
import struct

import pytest

from garmin_running.storage.repository import Repository


def crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def definition(local, global_number, fields):
    return (
        bytes([0x40 | local, 0, 0])
        + struct.pack("<H", global_number)
        + bytes([len(fields)])
        + b"".join(bytes(f) for f in fields)
    )


def synthetic_fit(*, distance=500000, serial=12345, duplicate=False, sessions=1):
    t = 1100000000  # FIT epoch; valor sintètic fix
    payload = definition(0, 0, [(3, 4, 0x8C), (4, 4, 0x86)])
    payload += bytes([0]) + struct.pack("<II", serial, t)
    payload += definition(
        1, 18, [(2, 4, 0x86), (5, 1, 0), (9, 4, 0x86), (7, 4, 0x86), (8, 4, 0x86)]
    )
    for _ in range(sessions):
        payload += bytes([1]) + struct.pack("<IBIII", t, 1, distance, 1500000, 1400000)
    payload += definition(2, 20, [(253, 4, 0x86), (3, 1, 2), (6, 2, 0x84), (5, 4, 0x86), (4, 1, 2)])
    for offset, hr, speed in [(0, 120, 3000), (1, 121, 3100), (11, 255, 0)]:
        payload += bytes([2]) + struct.pack("<IBHIB", t + offset, hr, speed, offset * 300, 85)
    if duplicate:
        payload += bytes([2]) + struct.pack("<IBHIB", t + 11, 145, 3200, 3300, 85)
    payload += definition(3, 21, [(253, 4, 0x86), (0, 1, 0), (1, 1, 0)])
    payload += bytes([3]) + struct.pack("<IBB", t + 11, 0, 4)
    header = struct.pack("<BBHI4s", 12, 0x20, 2100, len(payload), b".FIT")
    data = header + payload
    return data + struct.pack("<H", crc16(data))


@pytest.fixture
def fit_bytes():
    return synthetic_fit()


@pytest.fixture
def repo(tmp_path):
    repository = Repository(f"sqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "private")
    yield repository
    repository.engine.dispose()


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    """Una regressió de transport no pot convertir un mock en accés real."""

    def denied(*_args, **_kwargs):
        raise AssertionError("Xarxa real prohibida a la suite de proves")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
