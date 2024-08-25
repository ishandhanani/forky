from setuptools import setup, find_packages

setup(
    name='forky',
    version='0.1',
    packages=find_packages(),
    install_requires=[line.strip() for line in open('requirements.txt')],
    entry_points={
        'console_scripts': [
            'forky=cli.main:main',
        ],
    },
)
