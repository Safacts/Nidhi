from setuptools import setup, find_packages

setup(
    name='nidhi_sdk',
    version='0.2.2',
    description='Nidhi Storage & DB SDK — unified infrastructure client for FastAPI and Django',
    author='Aadisheshu',
    author_email='safacts001@gmail.com',
    packages=find_packages(),
    install_requires=[
        'minio',
        'boto3',
        'django-storages',
        'dj-database-url',
        'requests',
    ],
    python_requires='>=3.9',
)
