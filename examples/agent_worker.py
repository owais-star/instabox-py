"""
Agent Worker Pattern: Isolating heavy agent tasks in ephemeral Firecracker microVMs.
"""
from instabox import Sandbox, CommandExitError


def run_isolated_task(repo_url: str):
    print(f"🚀 Spawning isolated Firecracker sandbox for {repo_url}...")
    
    # Auto-kills sandbox on exit, or auto-suspends on idle
    with Sandbox.create("universal", on_exit="kill") as box:
        print(f"📦 Sandbox provisioned: {box.sandbox_id}")
        
        # Clone repo into isolated sandbox
        print("📥 Cloning repository...")
        box.commands.run(f"git clone --depth 1 {repo_url} /data/home/repo")
        
        # Run test suite without risking host environment
        print("🧪 Executing test suite...")
        try:
            res = box.commands.run("cd /data/home/repo && make test", timeout_seconds=180)
            print("✅ Tests passed:\n", res.stdout)
        except CommandExitError as e:
            print(f"❌ Test failed with exit code {e.exit_code}:\n{e.stderr}")


if __name__ == "__main__":
    # Example usage
    # run_isolated_task("https://github.com/example/solana-program")
    pass
