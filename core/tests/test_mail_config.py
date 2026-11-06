from config.mail import mailer_from_url


def test_smtp_url_with_tls():
    mailer = mailer_from_url("smtp+tls://user%40example.com:s3cret@mail.example.com:587")

    assert mailer == {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "mail.example.com",
            "port": 587,
            "username": "user@example.com",
            "password": "s3cret",
            "use_tls": True,
        },
    }


def test_smtp_url_with_ssl():
    mailer = mailer_from_url("smtp+ssl://mail.example.com:465")

    assert mailer["OPTIONS"] == {"host": "mail.example.com", "port": 465, "use_ssl": True}


def test_console_backend_has_no_options():
    assert mailer_from_url("consolemail://") == {
        "BACKEND": "django.core.mail.backends.console.EmailBackend"
    }
