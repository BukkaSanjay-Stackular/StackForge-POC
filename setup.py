from setuptools import setup, find_packages

setup(
    name="sdlc-pipeline",
    version="2.0.0",
    description="SDLC Pipeline: Automate requirements → design → user stories",
    author="Stackular AI",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "markitdown[all]",
        "requests",
        "pyyaml",
        "instructor>=1.5.0",
        "tenacity>=8.3.0",
        "tiktoken",
        "pydantic>=2.8.0",
        "pydantic-settings>=2.3.0",
        "typer>=0.12.0",
        "rich>=13.7.0",
        "loguru>=0.7.2",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "sdlc-pipeline=pipeline.cli:main",
        ],
    },
    python_requires=">=3.11",
)