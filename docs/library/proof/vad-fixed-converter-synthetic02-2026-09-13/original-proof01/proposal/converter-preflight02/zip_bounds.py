"""Two exact reviewed ZIP-boundary functions; no artifact paths or pickle parser."""
import struct
import zipfile

MAX_CD = 2 * 1024 * 1024
MAX_MEMBERS = 256
MAX_NAME = 256

class Refusal(Exception):
    def __init__(self, reason, *, directory_entry=None):
        super().__init__(reason)
        self.directory_entry = directory_entry

def require(condition, reason, *, directory_entry=None):
    if not condition:
        raise Refusal(reason, directory_entry=directory_entry)

def read_exact(stream, position, length, file_size):
    require(position >= 0 and 0 <= length <= MAX_CD, "Invalid or excessive metadata read")
    require(position + length <= file_size, "Metadata points outside the allowlisted file")
    stream.seek(position)
    value = stream.read(length)
    require(len(value) == length, "Truncated metadata read")
    return value


def directory_bounds(stream, file_size):
    tail_size = min(file_size, 65_557)
    tail = read_exact(stream, file_size - tail_size, tail_size, file_size)
    offset = tail.rfind(b"PK\x05\x06")
    require(offset >= 0 and offset + 22 <= len(tail), "A complete ZIP end record is required")
    eocd = file_size - tail_size + offset
    sig, disk, cd_disk, on_disk, count, cd_size, cd_offset, comment = struct.unpack("<4s4H2LH", tail[offset:offset + 22])
    require(eocd + 22 + comment == file_size, "Trailing or ambiguous ZIP end data refused")
    require(disk == cd_disk == 0, "Split ZIP archives are unsupported")
    locator_offset = eocd - 20
    locator = read_exact(stream, locator_offset, 20, file_size) if locator_offset >= 0 else b""
    zip64 = locator.startswith(b"PK\x06\x07")
    sentinel = on_disk == 0xFFFF or count == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF
    require(not sentinel or zip64, "ZIP64 metadata is missing")
    boundary = eocd
    if zip64:
        _, record_disk, record_offset, disks = struct.unpack("<4sLQL", locator)
        require(record_disk == 0 and disks == 1, "Split ZIP64 archives are unsupported")
        raw = read_exact(stream, record_offset, 56, file_size)
        fields = struct.unpack("<4sQ2H2L4Q", raw)
        zsig, record_size, made, needed, zdisk, zcd_disk, zon_disk, zcount, zsize, zoffset = fields
        require(zsig == b"PK\x06\x06" and 44 <= record_size <= 256, "Unsupported ZIP64 end record")
        require(record_offset + 12 + record_size == locator_offset, "ZIP64 end records overlap or disagree")
        require(zdisk == zcd_disk == 0 and zon_disk == zcount, "Split or inconsistent ZIP64 counts")
        for small, full, marker in ((on_disk, zon_disk, 0xFFFF), (count, zcount, 0xFFFF),
                                     (cd_size, zsize, 0xFFFFFFFF), (cd_offset, zoffset, 0xFFFFFFFF)):
            require(small == marker or small == full, "ZIP and ZIP64 directories disagree")
        count, cd_size, cd_offset = zcount, zsize, zoffset
        boundary = record_offset
    else:
        require(on_disk == count, "ZIP directory entry counts disagree")
    require(0 < count <= MAX_MEMBERS, "ZIP member count exceeds the inspection limit or is empty")
    require(0 < cd_size <= MAX_CD, "ZIP central directory exceeds the inspection limit")
    require(cd_offset > 0 and cd_offset + cd_size == boundary, "ZIP central-directory extent is inconsistent")
    require(read_exact(stream, 0, 4, file_size) == b"PK\x03\x04", "Prefixed or non-ZIP checkpoint refused")
    directory = read_exact(stream, cd_offset, cd_size, file_size)
    cursor = actual_count = 0
    while cursor < len(directory):
        require(actual_count < count, "Actual ZIP directory entry count exceeds advertised bound")
        require(cursor + 46 <= len(directory), "Truncated ZIP central-directory header")
        require(directory[cursor:cursor + 4] == b"PK\x01\x02", "Unsupported ZIP central-directory record")
        needed = struct.unpack_from("<H", directory, cursor + 6)[0]
        name_length, extra_length, comment_length, member_disk = struct.unpack_from("<4H", directory, cursor + 28)
        flags, method = struct.unpack_from("<2H", directory, cursor + 8)
        crc, packed, unpacked = struct.unpack_from("<3L", directory, cursor + 16)
        entry = {"ordinal": actual_count + 1, "central_header_offset": cd_offset + cursor,
                 "needed_version": needed, "made_version": struct.unpack_from("<H", directory, cursor + 4)[0],
                 "disk": member_disk, "compression_method": method, "flags": flags,
                 "crc32_u32": crc, "compressed_bytes_u32": packed, "uncompressed_bytes_u32": unpacked,
                 "name_bytes": name_length, "extra_bytes": extra_length, "comment_bytes": comment_length,
                 "local_header_offset_u32": struct.unpack_from("<L", directory, cursor + 42)[0]}
        stored_version_zero = (needed == 0 and entry["made_version"] == 0 and member_disk == 0
                               and method == zipfile.ZIP_STORED and flags == 2056)
        require((10 <= needed <= 45 or stored_version_zero) and member_disk == 0,
                "Unsupported or split ZIP directory entry",
                directory_entry=entry)
        require(0 < name_length <= MAX_NAME and extra_length <= 8192 and comment_length <= 1024,
                "ZIP central-directory member metadata exceeds limit", directory_entry=entry)
        cursor += 46 + name_length + extra_length + comment_length
        require(cursor <= len(directory), "ZIP central-directory entry extends outside directory",
                directory_entry=entry)
        actual_count += 1
    require(actual_count == count, "Actual ZIP directory entry count disagrees with advertised bound")
    return {"zip64": zip64, "members": count, "central_directory_bytes": cd_size, "central_directory_offset": cd_offset}


