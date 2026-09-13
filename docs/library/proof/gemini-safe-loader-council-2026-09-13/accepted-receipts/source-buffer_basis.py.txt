"""Unapproved analytic buffer consistency basis; no I/O or model packages."""
import math
import struct

ULP_LIMIT = 8
COUNT = 125
BYTE_COUNT = COUNT * 4


class BasisRefusal(ValueError):
    pass


def word(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def reference_words():
    window = tuple(word(0.54 - 0.46 * math.cos(2 * math.pi * i / 250)) for i in range(COUNT))
    time_vector = tuple(word(2 * math.pi * k / 16000) for k in range(-COUNT, 0))
    return window, time_vector


def exactly_one(little, big):
    if type(little) is not bool or type(big) is not bool:
        raise BasisRefusal("Invalid orientation decision")
    if little == big:
        raise BasisRefusal("Neither or both orientations satisfy the fixed basis")
    return "little" if little else "big"


def _matches(payload, references, endian):
    maximum = 0
    failures = 0
    for (candidate,), expected in zip(struct.iter_unpack(endian + "I", payload), references):
        if candidate & 0x7F800000 == 0x7F800000 or (candidate ^ expected) & 0x80000000:
            failures += 1
            continue
        distance = abs(candidate - expected)
        maximum = max(maximum, distance)
        if distance > ULP_LIMIT:
            failures += 1
    return failures == 0, failures, maximum


def compare_buffers(window, time_vector):
    if type(window) is not bytes or type(time_vector) is not bytes:
        raise BasisRefusal("Exactly two immutable byte strings required")
    if len(window) != BYTE_COUNT or len(time_vector) != BYTE_COUNT:
        raise BasisRefusal("Each buffer must contain exactly 500 bytes")
    references = reference_words()
    outcomes = {}
    for name, endian in (("little", "<"), ("big", ">")):
        first = _matches(window, references[0], endian)
        second = _matches(time_vector, references[1], endian)
        outcomes[name] = {
            "matches_both": first[0] and second[0],
            "window_failures": first[1],
            "time_vector_failures": second[1],
            "maximum_same_sign_finite_ulp_distance": max(first[2], second[2]),
        }
    orientation = exactly_one(outcomes["little"]["matches_both"], outcomes["big"]["matches_both"])
    return {
        "status": "consistent_with_unapproved_analytic_basis",
        "orientation": orientation,
        "word_count": 250,
        "ulp_limit": ULP_LIMIT,
        "orientations": outcomes,
        "writer_authenticated": False,
        "real_profile_approved": False,
        "other_storages_validated": False,
    }
