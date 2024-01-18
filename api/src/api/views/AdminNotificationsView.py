import json
import os

from flask import request

from api import app

from .decorators import is_admin


@app.route("/api/v3/admin/notification/template", methods=["PUT"])
@is_admin
def api_v3_admin_get_notification_template(payload):
    default_texts = {
        # event: default
        "email-verify": {
            "title": "Verify IsardVDI email",
            "body": """<p>Please verify your email address by clicking on the following button:</p>
                            <a href="{url}" class="btn btn-primary">Verify email</a>
                            <p>This button can only be used once and it's valid for 1 hour.</p>
                        """,
            "footer": "Please do not answer since this email has been automatically generated.",
            "channels": ["mail"],
        },
        "password-reset": {
            "title": "Reset IsardVDI password",
            "body": """<p>We've received your password reset request to access IsardVDI. Click on the following button to set a new password:</p>
                            <a href="{url}" class="btn btn-primary">Set password</a>
                            <p>This button can only be used once and it's valid for 24 hours.</p>
                            <p>If you did not initiate this request, you may safely ignore this message.</p>
                        """,
            "footer": "Please do not answer since this email has been automatically generated.",
            "channels": ["mail"],
        },
    }
    data = request.get_json()
    try:
        with open(
            os.path.join(app.EMAIL_TEMPLATES_ROUTE, "templates.json"), "r"
        ) as file:
            file_content = file.read()
        message = json.loads(file_content)[data["event"]]
        message["body"] = message["body"].format(**data["data"])
    except (KeyError, FileNotFoundError):
        message = default_texts[data["event"]]
        message["body"] = default_texts[data["event"]]["body"].format(**data["data"])

    return (
        json.dumps(message),
        200,
        {"Content-Type": "application/json"},
    )
