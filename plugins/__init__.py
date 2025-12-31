from aiohttp import web
from .route import routes

MAX_CLIENT_SIZE = 30 * 1024 * 1024  # 30 MB


async def create_web_app() -> web.Application:
    """
    Create and configure the aiohttp web application.
    """
    app = web.Application(client_max_size=MAX_CLIENT_SIZE)
    app.add_routes(routes)
    return app


# Backward compatibility
async def web_server() -> web.Application:
    return await create_web_app()