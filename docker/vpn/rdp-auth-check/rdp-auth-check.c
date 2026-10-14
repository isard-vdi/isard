// SPDX-License-Identifier: AGPL-3.0-or-later
// Check RDP credentials against a guest with NLA and disconnect before any session is created.
// Usage: rdp-auth-check <host> <port> <timeout-ms>, with username, password and domain on stdin.
// Prints one JSON line: {"result": "...", "error": <freerdp error>, "name": "<error name>"}.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <freerdp/error.h>
#include <freerdp/event.h>
#include <freerdp/freerdp.h>
#include <freerdp/settings.h>
#include <winpr/wlog.h>

#define STATE_NLA 2

// libfreerdp 2 fires this event but does not register it, so a subscriber never hears it unless it adds the type.
static wEventType state_event[] = { DEFINE_EVENT_ENTRY(ConnectionStateChange) };

static int saw_nla = 0;
static int passed_nla = 0;
static int skipped_nla = 0;

static void on_state(void* ctx, ConnectionStateChangeEventArgs* e)
{
	rdpContext* context = (rdpContext*)ctx;
	if (e->state == STATE_NLA)
	{
		saw_nla = 1;
		return;
	}
	if (e->state > STATE_NLA)
	{
		if (saw_nla)
			passed_nla = 1;
		else
			skipped_nla = 1;
		freerdp_abort_connect(context->instance);
	}
}

static void read_line(char* buf, size_t len)
{
	if (!fgets(buf, (int)len, stdin))
	{
		buf[0] = '\0';
		return;
	}
	buf[strcspn(buf, "\r\n")] = '\0';
}

static const char* classify(UINT32 error)
{
	if (passed_nla)
		return "ok";
	if (skipped_nla)
		return "no_nla";
	switch (error)
	{
		case FREERDP_ERROR_AUTHENTICATION_FAILED:
		case FREERDP_ERROR_CONNECT_LOGON_FAILURE:
		case FREERDP_ERROR_CONNECT_WRONG_PASSWORD:
		case FREERDP_ERROR_CONNECT_NO_OR_MISSING_CREDENTIALS:
			return "auth_failed";
		case FREERDP_ERROR_CONNECT_ACCOUNT_LOCKED_OUT:
		case FREERDP_ERROR_CONNECT_ACCOUNT_DISABLED:
		case FREERDP_ERROR_CONNECT_ACCOUNT_EXPIRED:
		case FREERDP_ERROR_CONNECT_PASSWORD_EXPIRED:
		case FREERDP_ERROR_CONNECT_PASSWORD_MUST_CHANGE:
		case FREERDP_ERROR_CONNECT_ACCOUNT_RESTRICTION:
		case FREERDP_ERROR_CONNECT_LOGON_TYPE_NOT_GRANTED:
			return "account_blocked";
		case FREERDP_ERROR_SECURITY_NEGO_CONNECT_FAILED:
		case FREERDP_ERROR_TLS_CONNECT_FAILED:
			return "security_refused";
		default:
			return "unreachable";
	}
}

int main(int argc, char** argv)
{
	char user[512], pass[512], domain[512];
	UINT32 error;
	freerdp* instance;
	rdpSettings* settings;

	if (argc != 4)
	{
		fprintf(stderr, "usage: %s <host> <port> <timeout-ms>\n", argv[0]);
		return 2;
	}
	read_line(user, sizeof(user));
	read_line(pass, sizeof(pass));
	read_line(domain, sizeof(domain));

	WLog_SetLogLevel(WLog_GetRoot(), WLOG_OFF);
	instance = freerdp_new();
	if (!instance || !freerdp_context_new(instance))
		return 3;
	settings = instance->settings;
	freerdp_settings_set_string(settings, FreeRDP_ServerHostname, argv[1]);
	freerdp_settings_set_uint32(settings, FreeRDP_ServerPort, (UINT32)atoi(argv[2]));
	freerdp_settings_set_uint32(settings, FreeRDP_TcpConnectTimeout, (UINT32)atoi(argv[3]));
	freerdp_settings_set_uint32(settings, FreeRDP_TcpAckTimeout, (UINT32)atoi(argv[3]));
	freerdp_settings_set_string(settings, FreeRDP_Username, user);
	freerdp_settings_set_string(settings, FreeRDP_Password, pass);
	if (domain[0])
		freerdp_settings_set_string(settings, FreeRDP_Domain, domain);
	freerdp_settings_set_bool(settings, FreeRDP_IgnoreCertificate, TRUE);
	freerdp_settings_set_bool(settings, FreeRDP_NlaSecurity, TRUE);
	freerdp_settings_set_bool(settings, FreeRDP_TlsSecurity, TRUE);
	freerdp_settings_set_bool(settings, FreeRDP_RdpSecurity, FALSE);
	freerdp_settings_set_bool(settings, FreeRDP_ExtSecurity, FALSE);
	PubSub_AddEventTypes(instance->context->pubSub, state_event, 1);
	PubSub_SubscribeConnectionStateChange(instance->context->pubSub, on_state);

	freerdp_connect(instance);
	error = freerdp_get_last_error(instance->context);
	memset(pass, 0, sizeof(pass));

	printf("{\"result\": \"%s\", \"error\": %u, \"name\": \"%s\"}\n", classify(error), error,
	       freerdp_get_last_error_name(error));
	freerdp_disconnect(instance);
	freerdp_context_free(instance);
	freerdp_free(instance);
	return 0;
}
