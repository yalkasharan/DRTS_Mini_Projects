from setuptools import setup, find_packages

setup(
    name="tsn-case-gen",
    description="TSN Test Case Generator",
    author="Jonathan Victor Flint, Oscar Svenstrup Nielsen",
    author_email="s224812@dtu.dk, s224770@dtu.dk",
    packages=find_packages(),
    py_modules=["tsn_case_gen", "topology_generator", "stream_generator", "route_generator", "validator", "UI", "utils_functions"],
    entry_points={
        "console_scripts": [
            "tsn-case-gen=tsn_case_gen:main",
        ],
    },
    install_requires=[
        "networkx>=3.0.0",
        "jsonschema>=4.0.0",
        "pydantic>=2.0.0",
        "pytest-mock>=3.14.0",
        "pytest>=8.3.5",
        "numpy>=2.2.5",
        "coverage>=7.4.0",
        "pytest-cov>=4.1.0"
    ],
    python_requires=">=3.8",
) 