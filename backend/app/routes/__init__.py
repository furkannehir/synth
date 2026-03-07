from flask_smorest import Api

api = Api()


def init_api(app):
    """Initialise flask-smorest Api and register every blueprint."""
    api.init_app(app)

    from app.routes.auth import blp as auth_blp
    api.register_blueprint(auth_blp)

    from app.routes.roles import blp as roles_blp
    api.register_blueprint(roles_blp)

    from app.routes.servers import blp as servers_blp
    api.register_blueprint(servers_blp)

    from app.routes.channels import blp as channels_blp
    api.register_blueprint(channels_blp)

    from app.routes.presence import blp as presence_blp
    api.register_blueprint(presence_blp)

    from app.routes.voice import blp as voice_blp
    api.register_blueprint(voice_blp)

    from app.routes.invites import blp as invites_blp
    api.register_blueprint(invites_blp)
