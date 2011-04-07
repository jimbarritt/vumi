import pycurl
from urlparse import urlparse
import logging
from decorator import decorator
from django.http import HttpResponse
try:
    # cStringIO is faster
    from cStringIO import StringIO
except ImportError:
    # otherwise this'll do
    from StringIO import StringIO

def specify_fields(model, include=[], exclude=[]):
    """
    Silly helper to allow me to specify includes & excludes using the model's
    fields as a base set instead of an empty set.
    """
    include.extend([field.name for field in model._meta.fields
                if field.name not in exclude])
    return exclude, include

def model_to_tuples(instance, exclude=[]):
    """
    Somewhat lame function to convert a model instance's fields & values to
    string values, ready for posting over HTTP
    
    >>> from django.db import models
    >>> class TestModel(models.Model):
    ...     __module__ = 'vumi.webapp.api.models'
    ...     integer = models.IntegerField(blank=True, null=True, default=1)
    ...     _float = models.FloatField(default=1.0)
    ...     created_at = models.DateTimeField(blank=True, auto_now_add=True)
    ...     updated_at = models.DateTimeField(blank=True, auto_now=True)
    ... 
    >>> model_to_tuples(instance=TestModel())
    (('id', 'None'), ('integer', '1'), ('_float', '1.0'), ('created_at', ''), ('updated_at', ''))
    >>> 
    
    """
    fields = [field for field in instance._meta.fields 
                if field.name not in exclude]
    resp = [(str(field.name), str(field.value_to_string(instance))) 
                for field in fields]
    return tuple(resp)

def model_to_dict(instance, exclude=[]):
    return dict(model_to_tuples(instance, exclude))

def _build_curl_object(url):
    """
    Helper function to set up a curl request object that does SSL
    verification & authentication.    
    """
    # parse the URL to get the username & password
    pr = urlparse(url)
    username = pr.username
    password = pr.password or '' # default to blank password, not None
    
    ch = pycurl.Curl()
    ch.setopt(pycurl.URL, str(url))
    ch.setopt(pycurl.VERBOSE, 0)
    ch.setopt(pycurl.SSLVERSION, 3)
    ch.setopt(pycurl.SSL_VERIFYPEER, 1)
    ch.setopt(pycurl.SSL_VERIFYHOST, 2)
    ch.setopt(pycurl.HTTPHEADER, [
            "User-Agent: Vumi Callback Client",
            "Accept:"
        ])
    ch.setopt(pycurl.FOLLOWLOCATION, 1)
    
    # if we're given a username, pass it along and let pycurl figure
    # out which Auth mechanism we're using, it'll automatically select
    # one pycurl thinks is most secure.
    if username:
        ch.setopt(pycurl.USERPWD, str('%s:%s' % (username,password)))
        ch.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_ANY)
    
    return ch
    

def utf8encode(tuples):
    return [(key.encode('utf-8'), value.encode('utf-8'))
        for key, value in tuples]

def callback(url, list_of_tuples, debug=False, debug_callback = False):
    """
    HTTP POST a list of key value tuples to the given URL and 
    return the response
    """
    
    ch = _build_curl_object(url)
    data = StringIO()
    ch.setopt(pycurl.WRITEFUNCTION, data.write)
    ch.setopt(pycurl.HTTPPOST, utf8encode(list_of_tuples))
    
    if debug:

        def _debug_handler(debug_type, debug_msg):
            logging.debug("pycurl:debug(%d): %s" % (debug_type, debug_msg))

        ch.setopt(pycurl.VERBOSE, 1)
        ch.setopt(pycurl.DEBUGFUNCTION, debug_callback or _debug_handler)

    try:
        result = ch.perform()
        resp = data.getvalue()
        logging.debug("Posting to %s which returned %s" % (url, resp))
        return (url, resp)
    except pycurl.error, e:
        logging.debug("Posting to %s resulted in error: %s" % (url, e))
        return (url, e)

def post_data_to_url(url,payload,content_type):
    """
    HTTP POST the data to the given URL with the correct content-type
    """
    data = StringIO()
    ch = _build_curl_object(url)
    ch.setopt(pycurl.WRITEFUNCTION, data.write)
    ch.setopt(pycurl.POSTFIELDS, payload)
    ch.setopt(pycurl.POSTFIELDSIZE, len(payload))
    
    try:
        result = ch.perform()
        resp = data.getvalue()
        logging.debug("Posting to %s which returned %s" % (url, resp))
        return (url, resp)
    except pycurl.error, e:
        logging.debug("Posting to %s resulted in error: %s" % (url, e))
        return (url, e)
    


def require_content_type(*content_types):
    """
    Decorator requiring a certain content-type. Like piston's require_mime but
    then without the silly hardcoded rewrite dict.
    """
    @decorator
    def wrap(f, self, request, *args, **kwargs):
        c_type_string = request.META.get('CONTENT_TYPE', None)
        if c_type_string:
            c_type_parts = c_type_string.split(";", 1)
            c_type = c_type_parts[0].strip()
            if not c_type in content_types:
                return HttpResponse(
                    "Bad Request, only '%s' allowed" % "', '".join(content_types), 
                    content_type='text/plain', 
                    status="400")
        return f(self, request, *args, **kwargs)
    return wrap

