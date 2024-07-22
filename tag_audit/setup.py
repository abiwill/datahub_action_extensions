from setuptools import find_packages, setup

setup(
    name="tag_audit",
    version="1.0",
    packages=find_packages(),
    # if you don't already have DataHub Actions installed, add it under install_requires
    install_requires=["acryl-datahub-actions", "gql[all]", "elasticsearch"],
    include_package_data=True,
    package_data={
        '': ['data/*.gql', 'data/*.json']
    },
    author="abhifrgn@gmail.com",
    description="Package to reapply tags that should not be deleted"
)
