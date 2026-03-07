from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager

# MongoDB instance — initialised in create_app()
mongo = PyMongo()

# JWT manager — initialised in create_app()
jwt = JWTManager()

# Media-server port — assigned during create_app()
# Will hold a concrete MediaServerPort implementation (e.g. LiveKitAdapter).
media_server = None
