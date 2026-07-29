// Package authentication implements the IsardVDI login orchestration for
// every identity provider (local, LDAP, SAML, Google, external applications
// and the form wrapper), including user auto-registration, the registration
// code flow and the sync of provider-owned fields on re-login.
//
// After a provider authenticates a user, startLogin applies the
// auto-registration policy. AutoRegister is the provider predicate that
// checks the auto_register flag and, when auto_register_roles is not empty,
// that the role is part of the list. It is evaluated over two different
// sources: the user data guessed from the IdP attributes (provided) and the
// user data stored in the database (dbUser).
//
//	                +------------------+
//	                | Login / Callback |
//	                +--------+---------+
//	                         |
//	     (form logins: p = the provider that actually
//	      authenticated the user, local or LDAP)
//	                         |
//	                         v
//	            +------------------------+
//	            | user exists in the DB? |
//	            +-----+------------+-----+
//	             no   |            |   yes
//	                  v            v
//	 +-------------------------+  +-------------------------+
//	 | AutoRegister(provided)? |  | AutoRegister(provided)? | (1)
//	 +-----+--------------+----+  +-----+---------------+---+
//	   yes |           no |         yes |            no |
//	       v              v             v               v
//	auto-register     sign a      overwrite the   +------------------------+
//	the groups and    register    role, groups    | AutoRegister(dbUser)?  | (2)
//	the user          token       and identity    +-----+--------------+---+
//	       |                           |            yes |           no |
//	       |                           |                v              v
//	       |                           |           sign a         refresh only
//	       |                           |           re-register    the identity
//	       |                           |           token          fields
//	       |                           |           (no login)          |
//	       v                           v                               v
//	+----------------------------------------------------------------------+
//	| finishLogin: disabled check, disclaimer, user migration, email       |
//	| verification, password reset, session creation and login token       |
//	+----------------------------------------------------------------------+
//
// When the data guessed from the IdP passes AutoRegister (1), the IdP is
// authoritative: the role, the primary and secondary groups and the identity
// fields are overwritten with the guessed values, even when the stored role
// is outside auto_register_roles. When only the stored data passes (2), the
// login is not completed: a re-register token is signed instead, and the new
// role and groups have to be applied through the registration code flow. The
// login stays blocked until the applied code moves the stored role out of
// auto_register_roles: finishReRegister re-evaluates the policy against the
// updated user with the IdP-guessed role frozen in the token and, when the
// restriction still holds, re-issues a re-register token. When neither passes,
// only the identity fields (name, username, photo and email) are refreshed.
//
// Form logins resolve the provider that actually authenticated the user
// before evaluating the policy, since the form wrapper would answer with the
// disjunction of every sub-provider. The resolution is scoped to the form
// wrapper: external users carry a synthetic provider name that would resolve
// to the unknown provider.
package authentication
