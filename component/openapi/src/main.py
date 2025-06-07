from fastapi import APIRouter, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
router = APIRouter()


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
            <img src="/openapi/cover-img.svg" alt="Cover Image"/>
          </div>
          <div class="right">
            <div class="logo">
              <img src="/custom/logo.svg" alt="Logo" style="max-width:180px;max-height:100px;">
            </div>
            <h1>IsardVDI OpenAPI Service</h1>
            <ul>
              <li><b>API v3</b>:
                <a href="/openapi/apiv3.json">openapi.json</a> |
                <a href="/openapi/docs/apiv3">Swagger UI</a> |
                <a href="/openapi/redoc/apiv3">ReDoc</a>
              </li>
              <!--
              <li><b>API v4</b>:
                <a href="/openapi/apiv4.json">openapi.json</a> |
                <a href="/openapi/docs/apiv4">Swagger UI</a> |
                <a href="/openapi/redoc/apiv4">ReDoc</a>
              </li>
              -->
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


# server cover-img.svg and favicon.ico
@router.get("/cover-img.svg", include_in_schema=False)
def cover_image():
    return FileResponse("cover-img.svg", media_type="image/svg+xml")


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("/favicon.ico", media_type="image/x-icon")


# Helper to serve JSON files
def serve_json(path):
    return FileResponse(path, media_type="application/json")


# --- API v3 ---
@router.get("/apiv3.json", include_in_schema=False)
def openapi_api():
    return serve_json("oas/api/api.json")


@router.get("/docs/apiv3", include_in_schema=False)
def docs_api():
    return get_swagger_ui_html(openapi_url="/openapi/api.json", title="API Swagger UI")


@router.get("/redoc/apiv3", include_in_schema=False)
def redoc_api():
    return get_redoc_html(openapi_url="/openapi/api.json", title="API ReDoc")


# --- API v4 ---
# @router.get("/apiv4.json", include_in_schema=False)
# def openapi_api():
#     return serve_json("oas/apiv4/apiv4.json")


# @router.get("/docs/apiv4", include_in_schema=False)
# def docs_api():
#     return get_swagger_ui_html(
#         openapi_url="/openapi/apiv4.json", title="API Swagger UI"
#     )


# @router.get("/redoc/api", include_in_schema=False)
# def redoc_api():
#     return get_redoc_html(openapi_url="/openapi/apiv4.json", title="API ReDoc")


# --- Authentication ---
@router.get("/authentication.json", include_in_schema=False)
def openapi_auth():
    return serve_json("oas/authentication/authentication.json")


@router.get("/docs/authentication", include_in_schema=False)
def docs_auth():
    return get_swagger_ui_html(
        openapi_url="/openapi/authentication.json", title="Authentication Swagger UI"
    )


@router.get("/redoc/authentication", include_in_schema=False)
def redoc_auth():
    return get_redoc_html(
        openapi_url="/openapi/authentication.json", title="Authentication ReDoc"
    )


# --- Notifier ---
@router.get("/notifier.json", include_in_schema=False)
def openapi_notifier():
    return serve_json("oas/notifier/notifier.json")


@router.get("/docs/notifier", include_in_schema=False)
def docs_notifier():
    return get_swagger_ui_html(
        openapi_url="/openapi/notifier.json", title="Notifier Swagger UI"
    )


@router.get("/redoc/notifier", include_in_schema=False)
def redoc_notifier():
    return get_redoc_html(openapi_url="/openapi/notifier.json", title="Notifier ReDoc")


app.include_router(router, prefix="/openapi")
