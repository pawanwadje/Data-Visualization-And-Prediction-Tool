# install_requirements.py
import subprocess
import sys

def install_requirements(file="requirements.txt"):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", file])
        print("✅ All requirements installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed: {e}")

if __name__ == "__main__":
    install_requirements()
