"""Exact generated ZIP fixture builder from the frozen converter harness."""
import struct
import zlib

def make_zip(payloads, *, flags=0, needed=20, descriptor64=False, descriptor_signature=True,
             zip64_end=False, local_zip64=False, central_zip64=False, padding=b"", gap_after_first=b""):
    body, central, positions = bytearray(), bytearray(), []
    for index, (name, payload) in enumerate(payloads):
        encoded = name.encode("utf-8")
        local = len(body)
        crc, length = zlib.crc32(payload) & 0xFFFFFFFF, len(payload)
        ver = 45 if local_zip64 or central_zip64 else needed
        extra = b""
        local_size = 0 if flags & 8 else length
        if local_zip64:
            extra += struct.pack("<HHQQ", 1, 16, local_size, local_size)
        if padding:
            extra += struct.pack("<HH", 0x4246, len(padding)) + padding
        body += struct.pack("<4s5H3I2H", b"PK\x03\x04", ver, flags, 0, 0, 0,
                            0 if flags & 8 else crc,
                            0xFFFFFFFF if local_zip64 else local_size,
                            0xFFFFFFFF if local_zip64 else local_size, len(encoded), len(extra))
        body += encoded + extra
        data_start = len(body)
        body += payload
        descriptor_start = len(body)
        if flags & 8:
            if descriptor_signature:
                body += b"PK\x07\x08"
            body += struct.pack("<IQQ" if descriptor64 else "<III", crc, length, length)
        if index == 0:
            body += gap_after_first
        central_extra = struct.pack("<HHQQQ", 1, 24, length, length, local) if central_zip64 else b""
        cstart = len(central)
        central += struct.pack("<4s6H3I5H2I", b"PK\x01\x02", ver, ver, flags, 0, 0, 0, crc,
                               0xFFFFFFFF if central_zip64 else length,
                               0xFFFFFFFF if central_zip64 else length,
                               len(encoded), len(central_extra), 0, 0, 0, 0,
                               0xFFFFFFFF if central_zip64 else local)
        central += encoded + central_extra
        positions.append({"name": name, "local": local, "data": data_start, "data_end": descriptor_start, "central_relative": cstart, "length": length})
    cd_offset, cd_size = len(body), len(central)
    body += central
    if zip64_end:
        record_offset = len(body)
        body += struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, len(payloads), len(payloads), cd_size, cd_offset)
        body += struct.pack("<4sLQL", b"PK\x06\x07", 0, record_offset, 1)
    body += struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0,
                        0xFFFF if zip64_end else len(payloads), 0xFFFF if zip64_end else len(payloads),
                        0xFFFFFFFF if zip64_end else cd_size, 0xFFFFFFFF if zip64_end else cd_offset, 0)
    for position in positions:
        position["central"] = cd_offset + position.pop("central_relative")
    return bytes(body), {"entries": positions, "cd_offset": cd_offset, "cd_size": cd_size}


