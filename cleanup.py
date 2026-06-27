import subprocess
from pathlib import Path

git = r"C:\Program Files\Git\bin\git.exe"

# Delete local copies
for f in ["cleaned_path.txt", "public_libraries/metabolomics_workbench_gcms.json"]:
    p = Path(f)
    if p.exists():
        p.unlink()
        print(f"Deleted: {f}")

# Remove from git tracking
for f in ["cleaned_path.txt", "public_libraries/metabolomics_workbench_gcms.json"]:
    subprocess.run([git, "rm", "--cached", "-f", f])

# Update gitignore
gi = Path(".gitignore")
content = gi.read_text()
for line in ["cleaned_path.txt", "public_libraries/metabolomics_workbench_gcms.json"]:
    if line not in content:
        content += f"\n{line}"
gi.write_text(content)

# Commit and push
subprocess.run([git, "add", "-A"])
subprocess.run([git, "commit", "-m", "Remove junk files"])
subprocess.run([git, "push"])

# Verify
r = subprocess.run([git, "ls-files"], capture_output=True, text=True)
print("Tracked files:")
for f in sorted(r.stdout.strip().split("\n")):
    print(f"  {f}")
