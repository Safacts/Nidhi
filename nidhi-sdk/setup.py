from setuptools import setup, find_packages

setup(
    name='nidhi_sdk',
    version='0.1.0',
    description='Nidhi Storage SDK — unified MinIO/S3 client for FastAPI and Django microservices',
    author='Aadisheshu',
    author_email='safacts001@gmail.com',
    packages=find_packages(),
    install_requires=[
        'minio',
        'boto3',
        'django-storages',
    ],
    python_requires='>=3.9',
)
