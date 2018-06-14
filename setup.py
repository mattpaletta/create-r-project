from distutils.core import setup
from setuptools import find_packages

requirements = []
with open('requirements.txt', "r") as requirements_file:
    for line in requirements_file:
        requirements.append(line)


setup(name='create-r-project',
      version='1.0',
      description='Create-R-Template and helper methods',
      author='Matthew Paletta',
      author_email='mattpaletta@gmail.com',
      url='https://www.python.org/sigs/distutils-sig/',
      packages=find_packages(),
      requires=requirements,
      entry_points={
          'console_scripts': [
              'create-r-project = r_utils.main:create_r_project',
              'sync-project = r_utils.main:perform_sync'
          ]
      },
      package_data={'r_utils': ['blank_rmd', 'argparse.yaml']},
)