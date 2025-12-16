import os
fifo_path = os.environ.get('XDG_RUNTIME_DIR') or "/tmp"
fifo_path = os.path.join(fifo_path, "mqttScript-logind.fifo")
_fifo_file: int | None = None
try:
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path, 0o600)
        print(f"Logind FIFO created at {fifo_path}")
    _fifo_file = os.open(fifo_path, os.O_WRONLY | os.O_NONBLOCK)
except Exception as e:
    print(f"Could not create FIFO at {fifo_path}: {e}")

if _fifo_file is not None:
    try:
        os.write(_fifo_file, b"TEST\n")
    except Exception as e:
        print(f"Could not write to FIFO at {fifo_path}: {e}")