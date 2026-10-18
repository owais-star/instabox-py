"""
Quickstart example for instabox-py.
"""
from instabox import Sandbox, CommandExitError

# 1. Connect to an existing sandbox or create a new one
# with Sandbox.create("universal") as box:
#     ...

box = Sandbox.connect("m_agqvbo2ftxhgsfdhy5c7wyjn7y", resume=False)

# 2. Run shell commands
res = box.commands.run("node -v && rustc --version")
print("Installed runtimes:\n", res.stdout)

# 3. Work with files
box.files.write("/data/home/greeting.txt", "Hello from instabox-py!")
content = box.files.read("/data/home/greeting.txt")
print("Read back:", content)

# 4. Check sandbox info
info = box.get_info()
print(f"Sandbox state: {info.state}, vCPU: {info.machine.get('spec', {}).get('vcpus')}")
