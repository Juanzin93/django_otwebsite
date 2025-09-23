from django.test import TestCase

# Create your tests here.
import socket, struct

def debug_otserver(host="192.168.1.105", port=7171):
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(b"\xFF\xFF")
        data = sock.recv(2)
        length = struct.unpack("!H", data)[0]
        payload = sock.recv(length)
        print("RAW RESPONSE:")
        print(payload.decode("utf-8", errors="ignore"))

debug_otserver()