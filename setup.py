from setuptools import setup, Extension

module = Extension(
    'minicov_tracer',
    sources=['src/tracer.c']
)

setup(
    name='minicov',
    version='1.0',
    description='MiniCoverage with C Tracer',
    ext_modules=[module]
)