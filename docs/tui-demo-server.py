#!/usr/bin/env python3
"""Serve a deterministic Dr Tulu response for the TUI demo recording."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

DEMO_RESPONSE = {
    "response": """# Mars: Three Established Facts

1. Mars is the fourth planet from the Sun and a terrestrial world with a rocky surface.
2. Its iron-rich minerals oxidize, giving the surface its familiar reddish appearance.
3. Mars has two small moons, Phobos and Deimos.

These facts are established through decades of telescopic observation and robotic exploration.""",
    "metadata": {
        "searched_links": [
            "https://science.nasa.gov/mars/",
            "https://science.nasa.gov/mars/moons/",
        ],
        "total_tool_calls": 2,
    },
}


class DemoRequestHandler(BaseHTTPRequestHandler):
    """Return the static report expected by the Dr Tulu backend."""

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        if self.path != "/chat":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(content_length)
        body = json.dumps(DEMO_RESPONSE).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Run the local demo server."""
    HTTPServer(("127.0.0.1", 8080), DemoRequestHandler).serve_forever()


if __name__ == "__main__":
    main()
