"""Extension build. Metadata lives in pyproject.toml.

setuptools still needs setup.py to declare ext_modules, so this file exists
only to compile the C cores under csrc/. One extension per env: a build that
links every env into one module would make a compile error in any env a
compile error in all of them.
"""

from setuptools import Extension, setup

CFLAGS = ["-O3", "-std=c11", "-Wall", "-Wextra"]

setup(
    ext_modules=[
        Extension(
            name="policyclash_envs._connect4",
            sources=["csrc/connect4_binding.c"],
            include_dirs=["csrc"],
            extra_compile_args=CFLAGS,
        ),
        Extension(
            name="policyclash_envs._tron_duel",
            sources=["csrc/tron_duel_binding.c"],
            include_dirs=["csrc"],
            extra_compile_args=CFLAGS,
        ),
        Extension(
            name="policyclash_envs._sap",
            sources=["csrc/sap_binding.c"],
            include_dirs=["csrc"],
            extra_compile_args=CFLAGS,
        ),
        Extension(
            name="policyclash_envs._sap2",
            sources=["csrc/sap2_binding.c"],
            include_dirs=["csrc"],
            extra_compile_args=CFLAGS,
        ),
    ],
)
