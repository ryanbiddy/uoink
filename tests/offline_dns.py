"""A public DNS answer for capture tests that fake the media process."""
import socket


def public_address(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port or 0))]
