import sys
from setuptools import setup, Extension, find_packages

module = Extension(
    'minicov_tracer',
    sources=['src/tracer.c'],
    optional=True,  # fallback for C compilation fails
)

# dependencies
install_requires = []
if sys.version_info < (3, 11):
    install_requires.append("tomli")

setup(
    name='minicov',
    version='1.0.0',
    description='A minimalist, high-performance (I hope) code coverage tool with MC/DC support and plans for further expansion.',
    author='Vitaliy Khomyn',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    ext_modules=[module],
    install_requires=install_requires,
    entry_points={
        'console_scripts': [
            'minicov=src.main:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Testing',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
    ],
    python_requires='>=3.10',
)
