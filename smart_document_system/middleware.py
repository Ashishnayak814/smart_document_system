import logging

from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth import load_backend
from django.contrib.auth.models import AnonymousUser
from django.core.signing import BadSignature
from django.http import HttpResponse
from django.utils.crypto import constant_time_compare
from django.utils.functional import SimpleLazyObject
from pymongo.errors import PyMongoError

from .mongodb import MongoConfigurationError

logger = logging.getLogger(__name__)


def _get_authenticated_user(request):
    """Load either a MongoDB-backed or legacy Django user from the session.

    Django's built-in helper coerces the session key through the default
    Django User model's integer primary key field. MongoUser uses a MongoDB
    ObjectId string, so that coercion raises a ValidationError after login.
    The backend stored in the session already knows how to resolve the ID.
    """
    user = None
    try:
        user_id = request.session[SESSION_KEY]
        backend_path = request.session[BACKEND_SESSION_KEY]
        backend = load_backend(backend_path)
        user = backend.get_user(user_id)

        if user is not None and HASH_SESSION_KEY in request.session:
            session_hash = request.session[HASH_SESSION_KEY]
            if not constant_time_compare(session_hash, user.get_session_auth_hash()):
                request.session.flush()
                user = None
    except (KeyError, ValueError, TypeError, BadSignature, AttributeError):
        request.session.flush()
        user = None
    return user or AnonymousUser()


class MongoAuthenticationMiddleware:
    """Authentication middleware compatible with MongoDB ObjectId sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: _get_authenticated_user(request))
        return self.get_response(request)


class MongoErrorMiddleware:
    """Keep Atlas connectivity/configuration errors out of frontend responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except (MongoConfigurationError, PyMongoError):
            logger.exception('MongoDB operation failed')
            return HttpResponse('The document service is temporarily unavailable. Please try again later.', status=503)
