"""Local ABP LoRaWAN 1.0 uplinks carried by Webots radio packets."""

import json
import os
import struct
from hmac import compare_digest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC

DEFAULT_DEVICE = "da1b0126"
PORT = 1
CHUNK_SIZE = 43
MAX_PARTS = 256
MAX_COUNTER_GAP = 16384


def session_key(name):
    return bytes.fromhex(os.environ[name])


def crypt_payload(key, device, counter, payload):
    blocks = b"".join(
        b"\x01" + bytes(5) + device + struct.pack("<I", counter) + bytes((0, block))
        for block in range(1, (len(payload) + 15) // 16 + 1)
    )
    cipher = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    stream = cipher.update(blocks) + cipher.finalize()
    return bytes(value ^ mask for value, mask in zip(payload, stream))


def mic(key, device, counter, message):
    cmac = CMAC(algorithms.AES(key))
    cmac.update(
        b"\x49" + bytes(5) + device + struct.pack("<I", counter)
        + bytes((0, len(message))) + message
    )
    return cmac.finalize()[:4]


class UplinkEncoder:
    def __init__(
        self,
        device_hex=DEFAULT_DEVICE,
        network_key_name="PERIMETER_NWK_SKEY",
        app_key_name="PERIMETER_APP_SKEY",
    ):
        self.device = bytes.fromhex(device_hex)
        self.header = b"\x40" + self.device + b"\x00"
        self.network_key = session_key(network_key_name)
        self.app_key = session_key(app_key_name)
        self.counter = 0

    def encode(self, result):
        payload = json.dumps(result, separators=(",", ":"), ensure_ascii=True).encode()
        return self.encode_bytes(payload)

    def encode_bytes(self, payload):
        parts = [payload[i:i + CHUNK_SIZE] for i in range(0, len(payload), CHUNK_SIZE)]
        if len(parts) > MAX_PARTS:
            raise ValueError("Edge result exceeds the local uplink limit")
        first_counter = self.counter
        for index, part in enumerate(parts):
            counter = self.counter
            self.counter += 1
            fragment = struct.pack("<IHH", first_counter, index, len(parts)) + part
            message = self.header + struct.pack("<HB", counter & 0xffff, PORT)
            message += crypt_payload(self.app_key, self.device, counter, fragment)
            yield message + mic(self.network_key, self.device, counter, message)


class UplinkDecoder:
    def __init__(
        self,
        device_hex=DEFAULT_DEVICE,
        network_key_name="PERIMETER_NWK_SKEY",
        app_key_name="PERIMETER_APP_SKEY",
        json_payload=True,
    ):
        self.device = bytes.fromhex(device_hex)
        self.header = b"\x40" + self.device + b"\x00"
        self.network_key = session_key(network_key_name)
        self.app_key = session_key(app_key_name)
        self.json_payload = json_payload
        self.counter = -1
        self.first = None
        self.parts = []

    def decode(self, frame):
        if not 22 <= len(frame) <= 64 or frame[:6] != self.header or frame[8] != PORT:
            return None
        low_counter = struct.unpack_from("<H", frame, 6)[0]
        counter = (max(self.counter, 0) & ~0xffff) | low_counter
        if counter <= self.counter:
            counter += 0x10000
        if counter - self.counter > MAX_COUNTER_GAP:
            return None
        if not compare_digest(frame[-4:], mic(self.network_key, self.device, counter, frame[:-4])):
            return None
        self.counter = counter
        fragment = crypt_payload(self.app_key, self.device, counter, frame[9:-4])
        first, index, total = struct.unpack_from("<IHH", fragment)
        if not 0 <= index < total <= MAX_PARTS or first + index != counter:
            return None
        if index == 0:
            self.first = first
            self.parts = []
        if self.first != first or index != len(self.parts):
            return None
        self.parts.append(fragment[8:])
        if len(self.parts) == total:
            payload = b"".join(self.parts)
            self.parts = []
            self.first = None
            return json.loads(payload) if self.json_payload else payload
        return None
