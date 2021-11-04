#
# wevis setuptools script
#
from setuptools import setup, find_packages

# Load text from readme
with open('README.md') as f:
    readme = f.read()

# Load version number
exec(open('wevis/_version.py').read())

# Go!
setup(
    # Module name (lowercase)
    name='wevis',
    version=__version__,

    # Description
    description='Client/Server IO for "Where\'s Ben Nevis".',
    long_description=readme,
    long_description_content_type='text/markdown',

    # License name
    license='BSD 3-clause license',

    # Maintainer information
    # author='',
    # author_email='',
    maintainer='Michael Clerx',
    maintainer_email='michael.clerx@nottingham.ac.uk',
    url='https://github.com/CardiacModelling/wevis',

    # Packages to include
    packages=find_packages(include=('wevis', 'wevis.*')),

    # Include non-python files (via MANIFEST.in)
    #include_package_data=True,

    # List of dependencies
    install_requires=[
    ],
    extras_require={
        'dev': [
            'flake8>=3',            # For code style checking
        ],
    },
    python_requires='>=3.6',
)
