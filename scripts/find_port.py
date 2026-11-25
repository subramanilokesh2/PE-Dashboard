"""Print the first free localhost port from a starting value (default 5055). UTF-8 safe, stdlib only."""
import socket, sys

def free_port(start=5055, tries=20):
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("No free port found between %d and %d." % (start, start + tries - 1))

if __name__ == "__main__":
    print(free_port(int(sys.argv[1]) if len(sys.argv) > 1 else 5055))
