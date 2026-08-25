import os
from html import escape as html_escape
from json import dumps as json_dumps

from fastapi import APIRouter, FastAPI
from fastapi.openapi.docs import get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

SWAGGER_JS_URL = "/openapi/static/swagger-ui-bundle.js"
SWAGGER_CSS_URL = "/openapi/static/swagger-ui.css"
SWAGGER_INIT_URL = "/openapi/static/swagger-init.js"
REDOC_JS_URL = "/openapi/static/redoc.standalone.js"
FAVICON_URL = "/favicon.ico"


def swagger_ui_html(openapi_url, title, config=None):
    """Swagger UI with no inline script, so `script-src 'self'` still renders it."""
    cfg = html_escape(json_dumps({"url": openapi_url, **(config or {})}))
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html>
  <head>
    <title>{html_escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="{SWAGGER_CSS_URL}">
    <link rel="shortcut icon" href="{FAVICON_URL}">
  </head>
  <body>
    <div id="swagger-ui" data-config="{cfg}"></div>
    <script src="{SWAGGER_JS_URL}"></script>
    <script src="{SWAGGER_INIT_URL}"></script>
  </body>
</html>"""
    )


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
router = APIRouter()

app.mount(
    "/openapi/static", StaticFiles(directory="/static", check_dir=False), name="static"
)


@router.get("/", include_in_schema=False)
def landing():
    return HTMLResponse(
        """
    <html>
      <head>
        <title>IsardVDI OpenAPI Service</title>
        <style>
          html, body {
            height: 100vh;
            margin: 0;
            padding: 0;
            font-family: sans-serif;
            background: #f8f9fa;
          }
          .container {
            display: flex;
            height: 100vh;
          }
          .left, .right {
            height: 100vh;
          }
          .left {
            flex: 1;
            background: #fff;
            display: flex;
            align-items: center;
            justify-content: center;
            border-right: 1px solid #eee;
            overflow: hidden;
          }
          .left img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
          }
          .right {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2em 1em;
            box-sizing: border-box;
          }
          .logo {
            margin-bottom: 2em;
          }
          h1 { color: #2c3e50; margin: 0 0 1em 0; }
          ul { line-height: 2; margin: 0; padding: 0; list-style: none; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="left">
            <img src="/openapi/static/cover-img.svg" alt="Cover Image"/>
          </div>
          <div class="right">
            <div class="logo">
              <img src="/api/v4/logo" alt="Logo" style="max-width:180px;max-height:100px;">
            </div>
            <h1>IsardVDI OpenAPI Service</h1>
            <ul>
              <li><b>API v4</b>:
                <a href="/api/v4/openapi.json">openapi.json</a> |
                <a href="/api/v4/docs">Swagger UI</a> |
                <a href="/api/v4/redoc">ReDoc</a>
              </li>
              <li><b>Authentication</b>:
                <a href="/openapi/authentication.json">openapi.json</a> |
                <a href="/openapi/docs/authentication">Swagger UI</a> |
                <a href="/openapi/redoc/authentication">ReDoc</a>
              </li>
              <li><b>Notifier</b>:
                <a href="/openapi/notifier.json">openapi.json</a> |
                <a href="/openapi/docs/notifier">Swagger UI</a> |
                <a href="/openapi/redoc/notifier">ReDoc</a>
              </li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """
    )


# Helper to serve JSON files
def serve_json(path):
    return FileResponse(path, media_type="application/json")


def swagger_page(name, title):
    return swagger_ui_html(f"/openapi/{name}.json", title)


def redoc_page(name, title):
    return get_redoc_html(
        openapi_url=f"/openapi/{name}.json",
        title=title,
        redoc_js_url=REDOC_JS_URL,
        redoc_favicon_url=FAVICON_URL,
        with_google_fonts=False,
    )


# --- Authentication ---
@router.get("/authentication.json", include_in_schema=False)
def openapi_auth():
    return serve_json("oas/authentication/authentication.json")


@router.get("/docs/authentication", include_in_schema=False)
def docs_auth():
    return swagger_page("authentication", "Authentication Swagger UI")


@router.get("/redoc/authentication", include_in_schema=False)
def redoc_auth():
    return redoc_page("authentication", "Authentication ReDoc")


# --- Notifier ---
@router.get("/notifier.json", include_in_schema=False)
def openapi_notifier():
    return serve_json("oas/notifier/notifier.json")


@router.get("/docs/notifier", include_in_schema=False)
def docs_notifier():
    return swagger_page("notifier", "Notifier Swagger UI")


@router.get("/redoc/notifier", include_in_schema=False)
def redoc_notifier():
    return redoc_page("notifier", "Notifier ReDoc")


def get_server_url():
    host = "develop.isardvdi.com"
    port = os.environ.get("HTTPS_PORT", "443")
    if port == "443":
        return f"https://{host}/openapi"
    else:
        return f"https://{host}:{port}/openapi"


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="IsardVDI OpenAPI Service",
        version="1.0.0",
        description="OpenAPI docs for IsardVDI",
        routes=app.routes,
    )
    openapi_schema["servers"] = [{"url": get_server_url()}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.include_router(router, prefix="/openapi")
