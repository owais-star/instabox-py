"""
Live integration test against running InstaBox sandbox.
Run with: INSTABOX_API_KEY=ibk_... python3 tests/test_live.py
"""
import os
import sys

from instabox import Sandbox, CommandExitError


def main():
    api_key = os.getenv("INSTABOX_API_KEY")
    if not api_key:
        print("INSTABOX_API_KEY is not set. Skipping live test.")
        sys.exit(0)

    print("⚡ Connecting to InstaBox Control Plane...")
    sandboxes = Sandbox.list(api_key=api_key)
    print(f"✅ Found {len(sandboxes)} active/provisioned sandboxes:")
    for s in sandboxes:
        print(f"  - [{s.sandbox_id}] {s.name} ({s.state})")

    if not sandboxes:
        print("No sandbox found to run live test.")
        return

    target = sandboxes[0]
    print(f"\n⚡ Attaching to target sandbox: {target.sandbox_id} ({target.name})...")
    box = Sandbox.connect(target.sandbox_id, resume=False, api_key=api_key)

    print("⚡ Executing live test command: echo...")
    res = box.commands.run("echo 'Hello from instabox-py SDK!'")
    print(f"✅ Output: {res.stdout.strip()}")
    assert "Hello from instabox-py SDK!" in res.stdout

    print("⚡ Executing system architecture check...")
    res_arch = box.commands.run("uname -m && lsb_release -d 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME")
    print(f"✅ Environment:\n{res_arch.stdout.strip()}")

    print("⚡ Testing atomic file write...")
    test_path = "/data/home/instabox_py_verification.txt"
    test_content = "Production SDK verification - Instabox-Py by Owais Iqbal\nTimestamp verified."
    box.files.write(test_path, test_content)
    assert box.files.exists(test_path), "File should exist after write"
    print("✅ File write confirmed.")

    print("⚡ Testing chunked file read...")
    read_back = box.files.read(test_path)
    assert read_back == test_content, f"Content mismatch: {read_back!r} vs {test_content!r}"
    print("✅ Content verified 100% identical.")

    print("⚡ Testing file removal...")
    box.files.remove(test_path)
    assert not box.files.exists(test_path), "File should not exist after remove"
    print("✅ File cleanly removed.")

    print("\n🎉 ALL LIVE SDK CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
