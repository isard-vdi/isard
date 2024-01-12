import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Pong")


def run(server_class=HTTPServer, handler_class=SimpleHTTPRequestHandler):
    httpd = HTTPServer(("0.0.0.0", 7899), SimpleHTTPRequestHandler)
    sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sslctx.check_hostname = False
    sslctx.load_cert_chain(
        certfile="/etc/pki/libvirt-spice/server-cert.pem",
        keyfile="/etc/pki/libvirt-spice/server-key.pem",
    )
    httpd.socket = sslctx.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()


if __name__ == "__main__":
    run()
