import os
import sys
import shutil
import subprocess


def clean_build():
    dirs_to_remove = ["build", "dist", "__pycache__"]
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Removed {dir_name}")

    for root, dirs, files in os.walk("."):
        for dir_name in dirs:
            if dir_name == "__pycache__":
                path = os.path.join(root, dir_name)
                shutil.rmtree(path)
                print(f"Removed {path}")


def build_exe():
    clean_build()

    pyinstaller_args = [
        "pyinstaller",
        "--name=Music++",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        f"--add-data=resources{os.pathsep}resources",
        f"--add-data=config{os.pathsep}config",
        "--hidden-import=PySide6",
        "--hidden-import=requests",
        "--hidden-import=mutagen",
        "--hidden-import=mutagen.mp3",
        "--hidden-import=mutagen.flac",
        "--hidden-import=mutagen.apev2",
        "--hidden-import=mutagen.oggvorbis",
        "--hidden-import=mutagen.wave",
        "--hidden-import=mutagen.m4a",
        "--icon=resources/icons/app.ico",
        "src/main.py",
    ]

    try:
        result = subprocess.run(pyinstaller_args, check=True)
        print("Build completed successfully!")
        print(f"Executable location: dist/Music++.exe")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        return False
    except FileNotFoundError:
        print("PyInstaller not found. Install with: pip install pyinstaller")
        return False


def build_dir():
    clean_build()

    pyinstaller_args = [
        "pyinstaller",
        "--name=Music++",
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        f"--add-data=resources{os.pathsep}resources",
        f"--add-data=config{os.pathsep}config",
        "--hidden-import=PySide6",
        "--hidden-import=requests",
        "--hidden-import=mutagen",
        "--icon=resources/icons/app.ico",
        "src/main.py",
    ]

    try:
        result = subprocess.run(pyinstaller_args, check=True)
        print("Build completed successfully!")
        print(f"Output location: dist/Music++/")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        return False
    except FileNotFoundError:
        print("PyInstaller not found. Install with: pip install pyinstaller")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dir":
        build_dir()
    else:
        build_exe()
