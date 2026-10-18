# instabox-py

Python SDK for [InstaBox](https://instabox.sh) (`insforge.dev`): provision ephemeral Linux microVMs (Firecracker), execute commands, transfer files, control virtual desktops (VNC/Chromium), capture snapshots, and orchestrate autonomous AI agent workers.

- **Zero Runtime Dependencies**: Built entirely on Python's standard library (`urllib.request`, `json`, `base64`). Runs seamlessly on Python 3.8+ without pulling external wheels.
- **Agent-Native & Fault-Tolerant**: Built-in exponential backoff retries, operation polling, idempotency keys, and context managers (`with Sandbox.create(...) as box:`).
- **100% Feature Parity**: Matches the official `@insforge/instabox-sdk` (TypeScript) API 1:1.

---

## Installation

```bash
pip install instabox-py
```

*Or install from source:*
```bash
git clone https://github.com/owais-star/instabox-py.git
cd instabox-py
pip install -e .
```

---

## Authentication

Set your API key in the environment:

```bash
export INSTABOX_API_KEY="ibk_..."
export INSTABOX_API_URL="https://api.instabox.sh"  # Optional, default
```

Or pass it directly when initializing:

```python
from instabox import Sandbox

box = Sandbox.create("universal", api_key="ibk_...")
```

---

## Quickstart

### 1. Provision and Run (Context Manager)

```python
from instabox import Sandbox

# Automatically provisions a 4 vCPU, 8 GB RAM Firecracker VM and terminates on exit
with Sandbox.create("universal", on_exit="kill") as box:
    print(f"Connected to sandbox: {box.sandbox_id}")
    
    # Run shell commands
    res = box.commands.run("node -v && rustc --version")
    print("Installed runtimes:\n", res.stdout)
    
    # Write and read files atomically
    box.files.write("/data/home/greeting.txt", "Hello from instabox-py!")
    content = box.files.read("/data/home/greeting.txt")
    print("Content:", content)
```

### 2. Connect to an Existing Sandbox

```python
from instabox import Sandbox

# Attach to an existing sandbox (resumes if paused/suspended)
box = Sandbox.connect("m_agqvbo2ftxhgsfdhy5c7wyjn7y", resume=False)

# Check machine specs and runtime status
info = box.get_info()
print(f"State: {info.state}, OS: {info.machine.get('template')}")
```

### 3. Background Commands (Detached Daemons)

```python
# Starts a daemon in its own process group with setsid nohup
server = box.commands.run("python3 -m http.server 8080", background=True)
print(f"Server PID: {server.pid}")

# Terminate process group when done
server.kill()
```

---

## Desktop GUI & Browser Automation

Sandboxes created from the default `agent-browser` template include an Xfce desktop, Chromium, and virtual display (`:1`).

```python
box = Sandbox.connect("m_...")

# Start desktop (1280x800)
box.desktop.start(width=1280, height=800)

# Open URL in headless Chromium
box.desktop.open("https://example.com")

# Capture full-screen PNG screenshot
png_bytes = box.desktop.screenshot()
with open("screenshot.png", "wb") as f:
    f.write(png_bytes)

# Mouse and keyboard automation
box.desktop.click(640, 400)
box.desktop.type("Search query\n")
box.desktop.press(["ctrl", "l"])

# Mint a public interactive VNC streaming link (valid 1 hour)
stream = box.desktop.stream_url(view_only=False, ttl_seconds=3600)
print(f"Watch live in browser: {stream.url}")
```

---

## MicroVM Lifecycle & Snapshots

| Method | Behavior | Memory / Processes | Disk State (`/data`) |
| :--- | :--- | :--- | :--- |
| `box.pause()` | Snapshot guest memory (suspend) | **Preserved** | **Preserved** |
| `box.resume()` | Restore execution from RAM snapshot | **Resumed** | **Preserved** |
| `box.stop()` | Clean OS shutdown | Terminated | **Preserved** |
| `box.kill()` | Permanent deletion | Terminated | **Deleted** |

### Snapshots & Golden Images

```python
# Save current disk state as a reusable golden image
snapshot = box.create_snapshot("solana-dev-ready", description="Anchor + Rust pre-installed")

# Clone fresh sandboxes in seconds from the snapshot
worker = Sandbox.create("sn_...")
```

---

## Agent Worker Pattern (Hub-and-Spoke Architecture)

```python
from instabox import Sandbox, CommandExitError

def execute_untrusted_audit(repo_url: str):
    """Run security audit or fuzz tests in isolated Firecracker microVM."""
    with Sandbox.create("universal", on_exit="kill") as worker:
        # Clone target
        worker.commands.run(f"git clone --depth 1 {repo_url} /data/home/target")
        
        # Execute tests without host credential exposure
        try:
            res = worker.commands.run(
                "cd /data/home/target && cargo test",
                timeout_seconds=300
            )
            return {"status": "success", "output": res.stdout}
        except CommandExitError as e:
            return {"status": "failed", "error": e.stderr, "exit_code": e.exit_code}
```

---

## Testing

Run unit tests (pure standard library):
```bash
python3 -m unittest discover -s tests -p "test_unit.py"
```

Run live integration verification against your active InstaBox fleet:
```bash
INSTABOX_API_KEY="ibk_..." python3 tests/test_live.py
```

---

## License

Apache License 2.0. Built by Owais Iqbal for the InstaBox & InsForge community.
