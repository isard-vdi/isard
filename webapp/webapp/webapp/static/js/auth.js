class InvalidTokenError extends Error {
}

InvalidTokenError.prototype.name = "InvalidTokenError";
function b64DecodeUnicode(str) {
    return decodeURIComponent(atob(str).replace(/(.)/g, (m, p) => {
        let code = p.charCodeAt(0).toString(16).toUpperCase();
        if (code.length < 2) {
            code = "0" + code;
        }
        return "%" + code;
    }));
}

function base64UrlDecode(str) {
    let output = str.replace(/-/g, "+").replace(/_/g, "/");
    switch (output.length % 4) {
        case 0:
            break;
        case 2:
            output += "==";
            break;
        case 3:
            output += "=";
            break;
        default:
            throw new Error("base64 string is not of the correct length");
    }
    try {
        return b64DecodeUnicode(output);
    }
    catch (err) {
        return atob(output);
    }
}

function jwtDecode(token, options) {
    if (typeof token !== "string") {
        throw new InvalidTokenError("Invalid token specified: must be a string");
    }
    options || (options = {});
    const pos = options.header === true ? 0 : 1;
    const part = token.split(".")[pos];
    if (typeof part !== "string") {
        throw new InvalidTokenError(`Invalid token specified: missing part #${pos + 1}`);
    }
    let decoded;
    try {
        decoded = base64UrlDecode(part);
    }
    catch (e) {
        throw new InvalidTokenError(`Invalid token specified: invalid base64 for part #${pos + 1} (${e.message})`);
    }
    try {
        return JSON.parse(decoded);
    }
    catch (e) {
        throw new InvalidTokenError(`Invalid token specified: invalid json for part #${pos + 1} (${e.message})`);
    }
}

function renewSession(sessionCookie) {
    $.ajax({
            url: '/authentication/renew',
            type: 'POST',
            contentType: 'application/json',
            headers: {
                'Authorization': 'Bearer ' + sessionCookie
            },
            async: false,
            data: JSON.stringify({}),
            // Otherwise it would use the ajaxSetup beforeSend
            beforeSend: function (jqXHR, settings) {
            },
            success: function (response) {
                saveCookie('isardvdi_session', response.token)
                let sessionData = jwtDecode(response.token)
                localStorage.setItem('auth_time_drift', (sessionData.iat * 1000) - Date.now())
            },
            // If it can't be renewed logout the user
            error: function (xhr, status, error) {
                window.location = '/isard-admin/logout'
            }
        });
}

function setAjaxHeader() {
    let sessionCookie = getCookie('isardvdi_session')
    $.ajaxSetup({
        url: "/api/v3",
        beforeSend: function (jqXHR, settings) {
            let sessionData = jwtDecode(sessionCookie)
            let timeDrift = Number(localStorage.getItem('auth_time_drift')) || 0;
            if (Date.now() + timeDrift > ((sessionData.exp - 30) * 1000)) {
                renewSession(sessionCookie)
                sessionCookie = getCookie('isardvdi_session')
            }
            jqXHR.setRequestHeader('Authorization', 'Bearer ' + sessionCookie)
            // TODO: remove url check
            if (settings.url.split("/")[1] == 'admin') {
                settings.url = "/api/v3" + settings.url
            }
            $("body").css("cursor", "wait");
            $("#send:not(:disabled)").addClass('ajaxDisabled').prop('disabled', true);
        },
        complete: function () {
            $("body").css("cursor", "");
            $("#send:disabled.ajaxDisabled").removeClass('ajaxDisabled').prop('disabled', false);
        },
    });

    // Ajax calls error handler for expired token error
    $(document).ajaxError(function (event, jqxhr, settings, thrownError) {
        if (jqxhr.status == 401 && jqxhr.responseJSON.error == 'unauthorized') {
            window.location = '/isard-admin/logout';
        }
    })
}

function saveCookie(name, value) {
    document.cookie = name + '=' + value + '; 0; path=/; secure; SameSite=None'
}

function getCookie(cookieName) {
    const cookiesArray = document.cookie.split('; ')

    for (let i = 0; i < cookiesArray.length; i++) {
        const cookie = cookiesArray[i]
        const cookieParts = cookie.split('=')
        const name = cookieParts[0].trim()
        const value = cookieParts[1]
        if (name === cookieName) {
            return decodeURIComponent(value)
        }
    }

    return null
}

function deleteCookie(cookieName) {
    document.cookie = cookieName + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;'
}

function listenCookieChange(callback, cookieName, interval = 1000) {
    let lastCookie = getCookie(cookieName)
    setInterval(() => {
        const cookie = getCookie(cookieName)
        if (cookie !== lastCookie) {
            try {
                callback(null, { oldValue: lastCookie, newValue: cookie }, cookieName)
            } finally {
                lastCookie = cookie
            }
        }
    }, interval)
}

function logout() {
    $.ajax({
        url: '/authentication/logout',
        type: 'POST',
        contentType: 'application/json',
        headers: {
            'Authorization': 'Bearer ' + getCookie('isardvdi_session')
        },
        data: JSON.stringify({}),
        success: function (response) {
            window.location = '/isard-admin/logout'
        },
        error: function (xhr, status, error) {
            window.location = '/isard-admin/logout'
        }
    });
}

$('#logout-btn').click(function () {
    logout()
})