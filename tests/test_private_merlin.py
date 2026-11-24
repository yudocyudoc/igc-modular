import json
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from tempfile import TemporaryDirectory
from pathlib import Path
from threading import Thread
from uuid import uuid4
from unittest.mock import patch
import hashlib

from arena.buffalo.private_merlin import private_merlin
from arena.common import ArenaError


class PrivateMerlinTest(unittest.TestCase):
    def test_reconnect_with_same_id(self):
        tasks = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.assert_client(self.headers["X-Arena-Client"], "private-merlin-v1")
                if self.path == "/submit":
                    tasks[body["task_id"]] = {**body, "status": "QUEUED"}
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(tasks[body["task_id"]]).encode())

            def log_message(self, *args):
                pass

        with TemporaryDirectory() as directory, HTTPServer(("127.0.0.1", 0), Handler) as server:
            server.assert_client = self.assertEqual
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                model = Path(directory) / "model.json"
                model.write_bytes(b'{}\n')
                task = str(uuid4())
                with self.assertRaises(ArenaError):
                    private_merlin("submit", "R", task, model, server.server_port)
                with patch("arena.buffalo.private_merlin.MODEL", hashlib.sha256(b"{}").hexdigest()):
                    first = private_merlin("submit", "R", task, model, server.server_port)
                    second = private_merlin("read", "R", task, port=server.server_port)
                    self.assertEqual(first, second)
            finally:
                server.shutdown()
                thread.join()
