# encoding: utf-8

import datetime
import logging
import re
import pysolr
import simplejson

from six import string_types
from six.moves.urllib.parse import quote_plus  # type: ignore
from typing import Any, Dict, Optional, Tuple
from pysolr import Solr

log = logging.getLogger(__name__)


class SearchIndexError(Exception):
    pass


class SearchError(Exception):
    pass


class SearchQueryError(SearchError):
    pass


DEFAULT_SOLR_URL = 'http://127.0.0.1:8983/solr'


class SolrSettings(object):
    _is_initialised: bool = False
    _url: Optional[str] = None
    _user: Optional[str] = None
    _password: Optional[str] = None

    @classmethod
    def init(cls,
             url: Optional[str],
             user: Optional[str] = None,
             password: Optional[str] = None) -> None:
        if url is not None:
            cls._url = url
            cls._user = user
            cls._password = password
        else:
            cls._url = DEFAULT_SOLR_URL
        cls._is_initialised = True

    @classmethod
    def get(cls) -> Tuple[str, Optional[str], Optional[str]]:
        if not cls._is_initialised:
            raise SearchIndexError('SOLR URL not initialised')
        if not cls._url:
            raise SearchIndexError('SOLR URL is blank')
        return (cls._url, cls._user, cls._password)


def is_available() -> bool:
    """
    Return true if we can successfully connect to Solr.
    """
    try:
        conn = make_connection()
        conn.search(q="*:*", rows=1)
    except Exception as e:
        log.exception(e)
        return False
    return True


def make_connection(decode_dates: bool = True) -> Solr:
    solr_url, solr_user, solr_password = SolrSettings.get()

    if solr_url and solr_user and solr_password:
        # Rebuild the URL with the username/password
        match = re.search('http(?:s)?://', solr_url)
        assert match
        protocol = match.group()
        solr_url = re.sub(protocol, '', solr_url)
        solr_url = "{}{}:{}@{}".format(protocol,
                                       quote_plus(solr_user),
                                       quote_plus(solr_password),
                                       solr_url)

    if decode_dates:
        decoder = simplejson.JSONDecoder(object_hook=solr_datetime_decoder)
        return pysolr.Solr(solr_url, decoder=decoder)
    else:
        return pysolr.Solr(solr_url)


def solr_datetime_decoder(d: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in d.items():
        if isinstance(v, string_types):
            possible_datetime = re.search(pysolr.DATETIME_REGEX, v)
            if possible_datetime:
                date_values: Dict[str, Any] = possible_datetime.groupdict()
                for dk, dv in date_values.items():
                    date_values[dk] = int(dv)

                d[k] = datetime.datetime(date_values['year'],
                                         date_values['month'],
                                         date_values['day'],
                                         date_values['hour'],
                                         date_values['minute'],
                                         date_values['second'])
    return d
