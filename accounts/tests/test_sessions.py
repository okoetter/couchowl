import time
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from accounts.middleware import SessionRenewalMiddleware
from accounts.models import User

KEY = SessionRenewalMiddleware.KEY
DAY = 24 * 3600


@pytest.fixture
def logged_in(client, db):
    user = User.objects.create_user(username="anna", password="pw-for-tests", region="DE")
    client.force_login(user)
    return client


def set_renewed_at(client, timestamp):
    session = client.session
    session[KEY] = timestamp
    session.save()


def expire_date(client):
    return Session.objects.get(session_key=client.session.session_key).expire_date


def test_first_visit_renews_the_login(logged_in):
    response = logged_in.get(reverse("core:dashboard"))

    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["max-age"] == settings.SESSION_COOKIE_AGE
    assert logged_in.session[KEY] == pytest.approx(time.time(), abs=60)


def test_visit_within_a_day_does_not_write_the_session(logged_in):
    set_renewed_at(logged_in, int(time.time()) - 3600)
    before = expire_date(logged_in)

    response = logged_in.get(reverse("core:dashboard"))

    assert settings.SESSION_COOKIE_NAME not in response.cookies
    assert expire_date(logged_in) == before


def test_visit_after_a_day_moves_the_expiry(logged_in):
    set_renewed_at(logged_in, int(time.time()) - 2 * DAY)
    Session.objects.filter(session_key=logged_in.session.session_key).update(
        expire_date=timezone.now() + timedelta(days=3)
    )

    response = logged_in.get(reverse("core:dashboard"))

    assert settings.SESSION_COOKIE_NAME in response.cookies
    expected = timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE)
    assert abs(expire_date(logged_in) - expected) < timedelta(minutes=1)


def test_anonymous_visitors_get_no_session(client, db):
    response = client.get(reverse("accounts:login"))

    assert settings.SESSION_COOKIE_NAME not in response.cookies
    assert not Session.objects.exists()
