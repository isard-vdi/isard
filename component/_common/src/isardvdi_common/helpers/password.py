import random
import string

import bcrypt
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r

from .error_factory import Error

SPECIAL_CHARACTERS = "!@#$%^&*()-_=+[]{};:'\",.<>?"


class Password(RethinkSharedConnection):
    """_From api/libv2/api_users.py Password"""

    @classmethod
    def valid(cls, plain_password, enc_password):
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), enc_password.encode("utf-8")
        )

    @classmethod
    def encrypt(cls, plain_password):
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    @classmethod
    def generate_human(cls, length=6):
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))

    @classmethod
    def generate_password(cls, policy):
        if not policy:
            raise ValueError("No policy provided")

        length = policy.get("length")
        min_uppercase = policy.get("uppercase")
        min_lowercase = policy.get("lowercase")
        min_digits = policy.get("digits")
        min_special = policy.get("special_characters")

        password_characters = []
        if min_uppercase:
            password_characters.extend(
                random.choices(string.ascii_uppercase, k=min_uppercase)
            )
        if min_lowercase:
            password_characters.extend(
                random.choices(string.ascii_lowercase, k=min_lowercase)
            )
        if min_digits:
            password_characters.extend(random.choices(string.digits, k=min_digits))
        if min_special:
            password_characters.extend(
                random.choices(SPECIAL_CHARACTERS, k=min_special)
            )

        remaining_length = length - len(password_characters)
        if remaining_length > 0:
            all_characters = string.ascii_letters + string.digits + string.punctuation
            password_characters.extend(
                random.choices(all_characters, k=remaining_length)
            )

        random.shuffle(password_characters)

        return "".join(password_characters)

    @classmethod
    def check_policy(cls, password, policy, user_id=None, username=None):
        if len(password) < policy["length"]:
            raise Error(
                "bad_request",
                "Password must be at least "
                + str(policy["length"])
                + " characters long",
                description_code="password_character_length",
                params={"num": policy["length"]},
            )

        if policy["uppercase"] > 0 and not any(
            char in string.ascii_uppercase for char in password
        ):
            raise Error(
                "bad_request",
                "Password must have at least "
                + str(policy["uppercase"])
                + " uppercase characters",
                description_code="password_uppercase",
                params={"num": policy["uppercase"]},
            )

        if policy["lowercase"] > 0 and not any(
            char in string.ascii_lowercase for char in password
        ):
            raise Error(
                "bad_request",
                "Password must have at least "
                + str(policy["lowercase"])
                + " lowercase characters",
                description_code="password_lowercase",
                params={"num": policy["lowercase"]},
            )

        if policy["digits"] > 0 and not any(char in string.digits for char in password):
            raise Error(
                "bad_request",
                "Password must have at least " + str(policy["digits"]) + " numbers",
                description_code="password_digits",
                params={"num": policy["digits"]},
            )

        if policy["special_characters"] > 0 and not any(
            char in SPECIAL_CHARACTERS for char in password
        ):
            raise Error(
                "bad_request",
                "Password must have at least "
                + str(policy["special_characters"])
                + " special characters: "
                + SPECIAL_CHARACTERS,
                description_code="password_special_characters",
                params={"num": policy["special_characters"]},
            )

        if user_id:  # new users do not have user_id
            with cls._rdb_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("username", "password_history")
                    .run(cls._rdb_connection)
                )
            username = user["username"]

            if policy["old_passwords"]:
                old_passwords = user["password_history"][
                    -min(policy["old_passwords"], len(user["password_history"])) :
                ]
                for pw in old_passwords:
                    if cls.valid(password, pw):
                        raise Error(
                            "bad_request",
                            "This password has already been used in the past",
                            description_code="password_already_used",
                        )
        if policy["not_username"] and username.lower() in password.lower():
            raise Error(
                "bad_request",
                "Password can not contain the username",
                description_code="password_username",
            )

        return True
