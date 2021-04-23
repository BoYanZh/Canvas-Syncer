from setuptools import find_packages, setup

setup(
    name="canvassyncer",
    version="2.0.1",
    description="A canvas file syner",
    url="https://github.com/BoYanZh/Canvas-Syncer",
    author="SJTU JI Tech",
    author_email="bomingzh@sjtu.edu.cn",
    packages=find_packages(),
    python_requires=">=3.6",
    entry_points={"console_scripts": ["canvassyncer=canvassyncer:main",],},
    project_urls={
        "Bug Reports": "https://github.com/BoYanZh/Canvas-Syncer/issues",
        "Source": "https://github.com/BoYanZh/Canvas-Syncer",
    },
    install_requires=["aiohttp", "aiofiles", "tqdm"],
)
