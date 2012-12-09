"""Defines website authentication helpers.
"""
import datetime
import rfc822
import time
import uuid

from aspen import Response
from aspen.utils import typecheck
from psycopg2.extras import RealDictRow


from gittip.orm import Session
from gittip.participant import Participant


BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week


class User(Participant):
    """Represent a website user.

    Every current website user is also a participant, though if the user is
    anonymous then the methods from Participant will fail with NoParticipantId.

    """

    def __init__(self, **kwargs):
        """Takes a dict of user info.
        """
        participant_id = kwargs.pop('id', None)
        Participant.__init__(self, participant_id, **kwargs)  # sets self.id

    @classmethod
    def from_session_token(cls, token):
        user = cls.query.filter(
            # TODO: Why are none of these working
            #            ~cls.is_suspicious == True,
            #            cls.is_suspicious != True,
            cls.session_token == token
        ).first()
        if user.is_suspicious:
            raise Exception('TODO: ')
        return user

    @classmethod
    def from_id(cls, participant_id):
        user = cls.query.filter(
            # TODO: Why are none of these working
#            ~cls.is_suspicious == True,
#            cls.is_suspicious != True,
            cls.id == participant_id
        ).one()
        if user.is_suspicious:
            raise Exception('TODO: ')
        user.session_token = uuid.uuid4().hex
        Session.commit()
        return user

    def __str__(self):
        return '<User: %s>' % getattr(self, 'id', 'Anonymous')
    __repr__ = __str__

    @property
    def ADMIN(self):
        return self.is_admin or False

    @property
    def ANON(self):
        return self.id is None


def inbound(request):
    """Authenticate from a cookie.
    """
    if 'session' in request.headers.cookie:
        token = request.headers.cookie['session'].value
        user = User.from_session_token(token)
    else:
        user = User()
    request.context['user'] = user


def outbound(response):
    from gittip import db
    user = None
    if 'user' in response.request.context:
        user = response.request.context['user']
        if not isinstance(user, User):
            raise Response(400, "If you define 'user' in a simplate it has to "
                                    "be a User instance.")

    if not user or not user.id:                     # user is anonymous
        if 'session' not in response.request.headers.cookie:
            # no cookie in the request, don't set one on response
            return
        else:
            # expired cookie in the request, instruct browser to delete it
            response.headers.cookie['session'] = ''
            expires = 0
    else:                                           # user is authenticated
        response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache
        response.headers.cookie['session'] = user.session_token
        expires = time.time() + TIMEOUT

        SQL = """
            UPDATE participants SET session_expires=%s WHERE session_token=%s
        """
        db.execute( SQL
            , ( datetime.datetime.fromtimestamp(expires)
                , user.session_token
              )
        )

    cookie = response.headers.cookie['session']
    # I am not setting domain, because it is supposed to default to what we
    # want: the domain of the object requested.
    #cookie['domain']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
