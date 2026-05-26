from setuptools import setup, find_packages

setup(
    name="musicpp",
    version="2.0.0",
    description="Music++ - Music Player Reconstructed with Python",
    author="Music++ Team",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "PySide6>=6.5.0",
        "requests>=2.31.0",
        "aiohttp>=3.8.0",
        "mutagen>=1.47.0",
        "numpy>=1.24.0",
        "pillow>=10.0.0",
    ],
    extras_require={
        "ai": [
            "openai-whisper>=20231117",
            "funasr>=1.0.0",
            "paddlespeech>=1.4.0",
        ],
        "dev": [
            "pyinstaller>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "musicpp=src.main:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio :: Players",
    ],
)
