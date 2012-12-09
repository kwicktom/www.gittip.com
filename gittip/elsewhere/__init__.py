import random

from aspen import log
from aspen.utils import typecheck
from gittip import db
from psycopg2 import IntegrityError


class AccountElsewhere(object):
    pass


class RunawayTrain(Exception):
    pass


def get_a_random_participant_id():
    """Return a random participant_id.

    The returned value is guaranteed to have been reserved in the database.

    """
    seatbelt = 0
    while 1:
        participant_id = hex(int(random.random() * 16**12))[2:].zfill(12)
        try:
            db.execute( "INSERT INTO participants (id) VALUES (%s)"
                      , (participant_id,)
                       )
        except IntegrityError:  # Collision, try again with another value.
            seatbelt += 1
            if seatbelt > 100:
                raise RunawayTrain
        else:
            break

    return participant_id.decode('US-ASCII')


def upsert(platform, user_id, username, user_info):
    """Given str, unicode, unicode, and dict, return unicode and boolean.

    Platform is the name of a platform that we support (ASCII blah). User_id is
    an immutable unique identifier for the given user on the given platform
    Username is the user's login/user_id on the given platform.  It is only
    used here for logging. Specifically, we don't reserve their username for
    them on Gittip if they're new here. We give them a random participant_id
    here, and they'll have a chance to change it if/when they opt in. User_id
    and username may or may not be the same. User_info is a dictionary of
    profile info per the named platform. All platform dicts must have an id key
    that corresponds to the primary key in the underlying table in our own db.

    The return value is a tuple: (participant_id [unicode], is_claimed
    [boolean], is_locked [boolean], balance [Decimal]).

    """
    typecheck( platform, str
             , user_id, (int, unicode)
             , username, unicode
             , user_info, dict
              )
    user_id = unicode(user_id)


    # Record the user info in our database.
    # =====================================

    INSERT = """\

        INSERT INTO elsewhere
                    (platform, user_id)
             VALUES (%s, %s)

    """
    try:
        db.execute(INSERT, (platform, user_id,))
    except IntegrityError:
        pass  # That login is already in our db.

    UPDATE = """\

        UPDATE elsewhere
           SET user_info=%s
         WHERE user_id=%s
     RETURNING participant_id

    """
    for k, v in user_info.items():
        # Cast everything to unicode. I believe hstore can take any type of
        # value, but psycopg2 can't.
        # https://postgres.heroku.com/blog/past/2012/3/14/introducing_keyvalue_data_storage_in_heroku_postgres/
        # http://initd.org/psycopg/docs/extras.html#hstore-data-type
        user_info[k] = unicode(v)
    rec = db.fetchone(UPDATE, (user_info, user_id))


    # Find a participant.
    # ===================

    if rec is not None and rec['participant_id'] is not None:

        # There is already a Gittip participant associated with this account.

        participant_id = rec['participant_id']
        new_participant = False

    else:

        # This is the first time we've seen this user. Let's create a new
        # participant for them.

        participant_id = get_a_random_participant_id()
        new_participant = True


    # Associate the elsewhere account with the Gittip participant.
    # ============================================================

    ASSOCIATE = """\

        UPDATE elsewhere
           SET participant_id=%s
         WHERE platform=%s
           AND user_id=%s
           AND (  (participant_id IS NULL)
               OR (participant_id=%s)
                 )
     RETURNING participant_id, is_locked

    """

    log(u"Associating %s (%s) on %s with %s on Gittip."
        % (username, user_id, platform, participant_id))
    rows = db.fetchall( ASSOCIATE
                      , (participant_id, platform, user_id, participant_id)
                       )
    rows = list(rows)
    nrows = len(rows)
    assert nrows in (0, 1)

    if nrows == 1:
        is_locked = rows[0]['is_locked']
    else:

        # Against all odds, the account was otherwise associated with another
        # participant while we weren't looking. Maybe someone paid them money
        # at *just* the right moment. If we created a new participant then back
        # that out.

        if new_participant:
            db.execute( "DELETE FROM participants WHERE id=%s"
                      , (participant_id,)
                       )

        rec = db.fetchone( "SELECT participant_id, is_locked "
                           "FROM elsewhere "
                           "WHERE platform=%s AND user_id=%s"
                         , (platform, user_id)
                          )
        if rec is not None:

            # Use the participant associated with this account.

            participant_id = rec['participant_id']
            is_locked = rec['is_locked']
            assert participant_id is not None

        else:

            # Okay, now this is just screwy. The participant disappeared right
            # at the last moment! Log it and fail.

            raise Exception("We're bailing on associating %s user %s (%s) with"
                            " a Gittip participant."
                            % (platform, username, user_id))

    rec = db.fetchone( "SELECT claimed_time, balance FROM participants "
                       "WHERE id=%s"
                     , (participant_id,)
                      )
    assert rec is not None
    return ( participant_id
           , rec['claimed_time'] is not None
           , is_locked
           , rec['balance']
            )
