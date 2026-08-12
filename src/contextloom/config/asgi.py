import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "contextloom.config.settings")

from django.core.asgi import get_asgi_application

django_application = get_asgi_application()


async def application(scope, receive, send):
    if scope["type"] == "lifespan":
        from contextloom.mcp_integration.server import mcp_application

        await mcp_application(scope, receive, send)
        return
    if scope["type"] == "http" and scope["path"] == "/mcp":
        from contextloom.mcp_integration.server import mcp_application

        await mcp_application(scope, receive, send)
        return
    await django_application(scope, receive, send)
