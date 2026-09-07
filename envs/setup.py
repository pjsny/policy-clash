"""Extension build. Metadata lives in pyproject.toml.

setuptools still needs setup.py to declare ext_modules, so this file exists
only to compile the C cores under csrc/.
"""

from setuptools import Extension, setup

setup(
    ext_modules=[
        Extension(
            name="policyclash_envs._connect4",
            sources=["csrc/binding.c"],
            include_dirs=["csrc"],
            extra_compile_args=["-O3", "-std=c11", "-Wall", "-Wextra"],
        ),
    ],
)
