"""Stream Pico USB serial telemetry to a live, phone-friendly web dashboard."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import threading
import time


PACKET_PREFIX = "PACKET:"
FIELD_PATTERN = re.compile(
    r"(?:^|,)\s*([^,:]+?)\s*:\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*([^\s,]*)"
)
DASHBOARD_PATH = Path(__file__).with_name("telemetry_dashboard.html")


class DashboardServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, ConnectionError):
            return
        super().handle_error(request, client_address)


def parse_packet(line):
    """Parse a telemetry line into numeric values and their optional units."""
    line = line.strip()
    payload = line[len(PACKET_PREFIX):] if line.startswith(PACKET_PREFIX) else line
    values = {}
    for match in FIELD_PATTERN.finditer(payload):
        name, raw_value, unit = match.groups()
        name = name.strip()
        if name:
            values[name] = {"value": float(raw_value), "unit": unit}
    return values or None


class TelemetryStore:
    def __init__(self, history_size=300):
        self._lock = threading.Lock()
        self._records = []
        self._history_size = history_size
        self._sequence = 0
        self._status = "Waiting for telemetry"

    def publish(self, values):
        with self._lock:
            self._sequence += 1
            self._records.append({
                "sequence": self._sequence,
                "timestamp": time.time(),
                "values": values,
            })
            if len(self._records) > self._history_size:
                self._records.pop(0)

    def set_status(self, status):
        with self._lock:
            self._status = status

    def snapshot(self):
        with self._lock:
            return self._records[:], self._sequence, self._status

    def after(self, sequence):
        with self._lock:
            return [record for record in self._records
                    if record["sequence"] > sequence], self._status


def make_handler(store, dashboard_html):
    class DashboardHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self.path == "/":
                body = dashboard_html
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                records, sequence, status = store.snapshot()
                try:
                    self._send_event("history", {
                        "records": records,
                        "status": status,
                    })
                    last_status = status
                    while True:
                        records, status = store.after(sequence)
                        if records:
                            for record in records:
                                sequence = record["sequence"]
                                self._send_event("packet", record)
                        if status != last_status:
                            self._send_event("status", {"status": status})
                            last_status = status
                        if not records:
                            self._send_event("heartbeat", {}, comment=True)
                            time.sleep(1)
                except ConnectionError:
                    return
            else:
                self.send_error(404)

        def _send_event(self, event, data, comment=False):
            if comment:
                self.wfile.write(b": keep-alive\n\n")
            else:
                payload = json.dumps(data, separators=(",", ":"))
                self.wfile.write(
                    "event: {}\ndata: {}\n\n".format(event, payload).encode("utf-8")
                )
            self.wfile.flush()

        def log_message(self, format_string, *args):
            if self.path != "/events":
                super().log_message(format_string, *args)

    return DashboardHandler


def main():
    parser = argparse.ArgumentParser(
        description="Show live Pico telemetry in a browser on your computer or phone."
    )
    parser.add_argument(
        "--serial-port",
        required=True,
        help="Pico USB serial port, for example COM5",
    )
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--http-port", type=int, default=8000)
    args = parser.parse_args()

    if not DASHBOARD_PATH.is_file():
        parser.error("Dashboard page not found: {}".format(DASHBOARD_PATH))
    dashboard_html = DASHBOARD_PATH.read_bytes()
    store = TelemetryStore()
    stop_event = threading.Event()

    try:
        import serial  # Check the dependency before starting the web server.
    except ImportError:
        parser.error(
            "pyserial is required. Install it with: "
            "python -m pip install -r requirements-dashboard.txt"
        )

    try:
        connection = serial.Serial(args.serial_port, baudrate=args.baudrate, timeout=1)
    except serial.SerialException as error:
        parser.error("Could not open serial port {}: {}".format(args.serial_port, error))

    store.set_status(
        "Connected to {}; waiting for serial output".format(args.serial_port)
    )

    class SerialReader(threading.Thread):
        def run(self):
            print("Reading telemetry from {} at {} baud.".format(
                args.serial_port, args.baudrate
            ))
            last_serial_data = time.time()
            reported_timeout = False
            try:
                while not stop_event.is_set():
                    raw_line = connection.readline()
                    if not raw_line:
                        if (
                            not reported_timeout
                            and time.time() - last_serial_data >= 5
                        ):
                            store.set_status(
                                "No serial data received from {}".format(args.serial_port)
                            )
                            print(
                                "No serial data received from {}. Check the Pico USB "
                                "connection and make sure this is the Pico's COM port."
                                .format(args.serial_port)
                            )
                            reported_timeout = True
                        continue
                    last_serial_data = time.time()
                    reported_timeout = False
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    print("Serial: {!r}".format(line))
                    values = parse_packet(line)
                    if values is not None:
                        store.publish(values)
                        store.set_status(
                            "Receiving telemetry from {}".format(args.serial_port)
                        )
                        print("Telemetry: {}".format(values))
                    elif line.startswith(PACKET_PREFIX):
                        store.set_status("Could not parse packet: {}".format(line[:160]))
                        print("Could not parse telemetry packet: {}".format(line))
                    else:
                        store.set_status("Could not parse serial line: {}".format(line[:160]))
            except (serial.SerialException, OSError) as error:
                store.set_status("Serial read error: {}".format(error))
                print("Serial read error: {}".format(error))
            finally:
                connection.close()

    reader = SerialReader(daemon=True)
    server = DashboardServer(
        ("0.0.0.0", args.http_port), make_handler(store, dashboard_html)
    )
    print("Dashboard on this computer: http://localhost:{}".format(args.http_port))
    print("To open it on your phone, use this computer's IPv4 address and port {}.".format(
        args.http_port
    ))
    print("Keep the Pico connected and both devices on the same Wi-Fi network.")
    reader.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()
        connection.close()
        reader.join(timeout=2)


if __name__ == "__main__":
    main()
