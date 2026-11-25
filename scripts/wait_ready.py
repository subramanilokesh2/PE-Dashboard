"""Poll the local server until it answers /api/meta or the timeout expires. Exit code 0 when ready."""
import sys, time, urllib.request

def main(url, timeout_s=40):
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    print("Server is ready at", url)
                    return 0
        except Exception:
            time.sleep(0.5)
    print("The server did not start within %d seconds. Check the server window for errors." % timeout_s)
    return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
