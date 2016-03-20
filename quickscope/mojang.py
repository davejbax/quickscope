import http.client
import urllib.parse
import json
import http.cookies
import time
from collections import namedtuple

# ========================================
#
#               CONSTANTS
#
# ========================================
Url = namedtuple('Url', ['ssl', 'host', 'port', 'path'])

# API endpoint to fetch name history for a player
URL_NAMES   = Url(True, 'api.mojang.com', 443, '/user/profiles/{uuid}/names')

# API endpoint to fetch holder of a username at a time
URL_UUID_AT = Url(True, 'api.mojang.com', 443, '/users/profiles/minecraft/{username}?at={timestamp}')

# Login form to obtain session to change username
URL_LOGIN = Url(True, 'account.mojang.com', 443, '/login')

# Rename profile endpoint
URL_RENAME_PROFILE = Url(True, 'account.mojang.com', 443, '/me/renameProfile/{uuid}')

# Dummy User-Agent string
USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36'

# ========================================
#
#               HELPERS
#
# ========================================
def create_connection(url):
    """Creates an HTTPConnection or HTTPSConnection instance using the
    parameters in the Url `url`.

    Keyword arguments:
    url -- Url tuple
    """
    
    if url.ssl:
        conn = http.client.HTTPSConnection(url.host, url.port)
        #conn.set_tunnel(url.host, url.port)
        return conn
    else:
        return http.client.HTTPConnection(url.host, url.port)

def get_cookies(headers):
    """Obtains cookies from a set of HTTP headers. The headers are scanned
    for a 'Set-cookie:' header. If found, this is then parsed into an http.cookies.SimpleCookie()
    This 'cookie jar' then contains all of the cookies found within the headers.

    Keyword arguments:
    headers -- Array of (key, value) headers

    Returns a http.cookies.SimpleCookie() instance
    """
    
    cookie_headers = [ header[1] for header in headers if header[0].lower() == 'set-cookie' ]
    cookie_jar     = http.cookies.SimpleCookie()
    for h in cookie_headers:
        cookie_jar.load(h)
    return cookie_jar

def get_login_error(result):
    """Convenience function to parse the result of calling mojang#login.

    Keyword arguments:
    result -- Result returned from calling mojang#login or mojang#api_login

    Returns a string with a descriptive message of the error if any were
    detected. Otherwise, None is returned (indicating success).
    """
    
    if not result: # Failure to get auth token if result is none
        return 'Failed to get authenticity token'
    elif result[0] != 200 and result[0] != 302: # Some failure if wrong response code
        return 'Unrecognized response code: {}'.format(result[0])
    elif len([ header for header in result[1] if header[0].lower() == 'location' and header[1].lower()[-6:] == URL_LOGIN.path ]) > 0: # Incorrect login if redirecting to /login
        return 'Incorrect login'
    else:
        return None

# ========================================
#
#              API FUNCTIONS
#
# ========================================
def api_uuid_at(username, timestamp):
    """Sends an HTTP(S) request to the Mojang API to retrieve the UUID of
    a player at the given time. If the player's name has not changed and
    the account is not legacy, a response code of 204 is returned.

    Keyword arguments:
    username  -- Username of player to find UUID of
    timestamp -- Unix timestamp (seconds) of the time to check for the player's
                 UUID at. 0 seconds will retrieve the original username.

    Returns a tuple of (status code, data) (where data is binary string of JSON)
    """
    conn = create_connection(URL_UUID_AT)

    # Send request
    conn.request('GET', URL_UUID_AT.path.format(username=username, timestamp=timestamp))
    resp = conn.getresponse()

    # Read response
    data = resp.read()
    
    return (resp.status, data)

def api_names(uuid):
    """Sends an HTTP(S) request to the Mojang API to retrieve all the username
    changes of a player of the given UUID `uuid`. UUID must be without hyphens.

    Keyword arguments:
    uuid -- UUID of player to find name history of (without hyphens)

    Returns a tuple of (status code, data) (where data is a binary string of JSON)
    """
    conn = create_connection(URL_NAMES)

    # Send request
    conn.request('GET', URL_NAMES.path.format(uuid=uuid))
    resp = conn.getresponse()

    # Read response
    data = resp.read()

    return (resp.status, data)

def api_get_login():
    """Sends a GET request to the /login endpoint on Mojang's accounts site.
    Note that this does not actually do any logging in, it just loads the page.
    This is required to obtain an authenticity token, which is used to login.

    The authenticity token can be obtained from this function by calling the
    get_authenticity_token function with the returned headers as the parameter.

    Returns a tuple of (status code, headers), where headers is a (key,value) list.
    """
    
    conn = create_connection(URL_LOGIN)

    conn.request('GET', URL_LOGIN.path, None, { 'User-Agent': USER_AGENT })
    resp = conn.getresponse()

    return (resp.status, resp.getheaders())

def api_login(username, password, authenticity_token):
    """Attempts to login to Mojang and create a session with the given
    username, password, and authenticity token (a CSRF-like token, which
    can be obtained with mojang#get_authenticity_token).

    The request is a POST request with the given data and an extra parameter
    'remember' set to true (to keep the session).

    The request is sent and the response obtained. The data of the response,
    however, is ignored, as it does not provide any meaningful information
    of whether the login succeeded.

    Keyword arguments:
    username -- Username of Mojang account
    password -- Password of Mojang account
    authenticity_token -- (string) An authenticity token; see mojang#get_authenticity_token

    Returns a tuple of (response status code, response headers)
    """
    
    conn = create_connection(URL_LOGIN)

    # Send request with parameters to login and fake User-Agent string
    conn.request('POST', URL_LOGIN.path, urllib.parse.urlencode({
        'username': username,
        'password': password,
        'authenticityToken': authenticity_token,
        'remember': 'true'
    }),
    {
        'User-Agent': USER_AGENT,
        'Referer': 'https://account.mojang.com/login',
        'Origin': 'https://account.mojang.com',
        'Accept-Encoding': 'gzip, deflate',
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    resp = conn.getresponse()

    return (resp.status, resp.getheaders())

def api_get_rename_profile(uuid, login_cookies):
    """Sends a GET request for the rename profile page. This does not
    actually request to rename the profile, contrary to the function name.
    This can be used to obtain an authenticity token that can be used to
    actually rename the profile.

    To obtain an authenticity token from the result of this function, simply
    call mojang#get_authenticity_token with the parameter `result[1]`, where
    result is the result of calling this function.

    Keyword arguments:
    uuid -- UUID of Minecraft account
    login_cookies -- Login cookies (see mojang#get_cookies). Needed as this is a restricted area of the site.

    Returns a tuple of (response status code, response headers)
    """
    
    conn = create_connection(URL_RENAME_PROFILE)

    conn.request('GET', URL_RENAME_PROFILE.path.format(uuid=uuid), None, {
        'User-Agent': USER_AGENT,
        'Cookie': login_cookies.output(attrs=[], header='', sep='; ')
    })
    resp = conn.getresponse()

    return (resp.status, resp.getheaders())

# ========================================
#
#           LOGICAL FUNCTIONS
#  (ones that do something with the API)
#
# ========================================
def get_free_time(username, prev_time = 0):
    """Gets the time at which a username was 'freed' from a user.
    This is the latest time when the user who owns the username
    changed their name to something else, thus 'freeing' the username
    if they do not change it back within 37 days. Note that the
    37 days are not added on to the returned values.

    This function involves several requests to the Mojang API
    in order to work out when the username was 'freed', and so is a
    costly function.

    Note that requests to Mojang APIs are rate limited to 600 requests
    per 10 minutes. The number of requests that this function involves
    is unknown, and could possibly exceed this.

    If retrieving this information is not possible, a value of None is
    returned. Reasons for this return value:
    - Failure to send request to Mojang API
    - Username does not exist
    - Username was not changed, and account is not legacy
    - Rate limit exceeded

    If the function succeeds, a Unix timestamp is returned giving the
    number of seconds since the epoch when the last owner of the
    username changed their name to something else, thus freeing the
    name. Adding 37 days to this value will yield the time that a
    username becomes freely available to register.
    """
    # Get UUID at time
    (code, data) = api_uuid_at(username, prev_time)

    # If we hit a non-OK response, return the previous UUID
    # - this can indicate that it is not possible to get their
    # UUID (due to non-legacy/no name changes) or that we hit the
    # latest record for it, which is that nobody owns the name
    if code != 200:
        # Subtract 1 from prev_time as 1 was added
        return None if prev_time == 0 else prev_time - 1

    # Ensure data is not empty at this point
    if len(data) == 0:
        return None

    # Parse JSON data    
    json_data = json.loads(data.decode())
    uuid = json_data['id']

    # Get player's username history
    (code, data) = api_names(uuid)

    # Function failed; UUID is invalid (should be impossible) or Mojang
    # didn't feel like giving us a meaningful response. 
    if code != 200:
        return None

    if len(data) == 0:
        return None

    # Parse JSON data and sort by changed date
    history    = json.loads(data.decode())
    changed_to = 0
    prev_name  = ''

    # Iterate over each username change
    for change in history:

        # Update changed to if the previous name was the username
        # and the changed to time is greater than our stored one
        if prev_name.lower() == username.lower() \
        and 'changedToAt' in change \
        and change['changedToAt'] > changed_to:
            changed_to = change['changedToAt']
            
        prev_name = change['name']

    # If the username has been changed from the one we want, recursively
    # call this function with the time it was changed + 1 second (to get
    # the new username owner).
    if changed_to > 0:
        return get_free_time(username, (changed_to // 1000) + 1)
    else:
        return None

def get_authenticity_token(headers):
    """Attempts to retrieve an authenticity token from a set of
    headers.

    The authenticity token should exist in a 'Set-cookie:' header.
    These headers are parsed via the http.cookies module, and then
    scanned for a 'PLAY_SESSION' cookie. This cookie contains a
    query string, which is then parsed and scanned for the key '___AT'.

    Keyword arguments:
    headers -- a (key, value) array of headers

    If the authenticity token is found, it is returned as a string.
    Otherwise, None is returned.
    """
    
    cookies = get_cookies(headers)
    
    # Ensure we have an auth token
    if not 'PLAY_SESSION' in cookies:
        return None

    # Attempt to get authentication token from session cookie
    session = cookies['PLAY_SESSION'].value
    parts   = urllib.parse.parse_qs(session)

    # Return none if non-existent
    if not '___AT' in parts:
        return None
    
    return parts['___AT'][0]

def login(username, password):
    """Attempts to login to Mojang (accounts.mojang.com) using the
    given username and password.

    This will first send a request to obtain an 'authenticity token'
    (presumably used for preventing CSRF), and will then attempt the login
    with another request.

    This will return a tuple of (status, headers, body). Note that headers
    will contain session information that is needed for authorized
    requests. The get_cookies function is useful in obtaining this information
    from the returned headers (a list of (key, value) tuples).

    If the login could not be executed due to a failure to get the auth token,
    False is returned.
    """
    
    # Send a request to get an auth token (for CSRF)
    (status, headers) = api_get_login()
    at = get_authenticity_token(headers)

    if at is None:
        return False
    
    # Attempt to login
    return api_login(username, password, at)

def rename_profile_later(username, password, uuid, new_name, login_cookies = None):
    """Prepares a request to rename a profile. This will login, if necessary (i.e
    if login_cookies is None); get an authenticity token to rename the profile;
    create an HTTP(S) connection to rename a profile; prepare the headers and data
    to be sent with the request; and create an anonymous function that will send
    the request.

    Note that the request is not actually sent - the function to send it is returned
    from this function, so that the request can be sent 'later'.

    Keyword arguments:
    username -- Mojang username
    password -- Mojang password
    uuid -- UUID of Minecraft account
    new_name -- New (desired) username
    login_cookies -- (optional) login cookies obtained via calling mojang#get_cookies on a login response

    Returns a tuple of (f, connection, login_cookies), where:
       f -- anonymous function f(connection), where connection is an http.client.HTTP(S)Connection
       connection -- HTTPSConnection instance obtained via create_connection; connected to rename profile page
       login_cookies -- The generated login cookies, if none were passed.
    """
    
    # Login if needed to
    if login_cookies is None:

        # Attempt login
        result = login(username, password)

        # Handle errors
        error = get_login_error(result)
        if error is not None:
            return (False, error, None)
        
        # Store login cookies
        login_cookies = get_cookies(result[1])

    # Get authenticity token for renaming profile
    (status, headers) = api_get_rename_profile(uuid, login_cookies)
    at = get_authenticity_token(headers)

    # Handle failure to get auth token
    if at is None:
        return (False, 'Failed to get second authenticity token', None)

    # Create parameters for request to rename profile in advance
    conn = create_connection(URL_RENAME_PROFILE)
    path = URL_RENAME_PROFILE.path.format(uuid=uuid)
    data = urllib.parse.urlencode({
        'newName': new_name,
        'password': password,
        'authenticityToken': at
    })
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cookie': get_cookies(headers).output(attrs=[], header='', sep='; ')
    }

    def execute(conn):
        conn.request('POST', path, data, headers)

    return (execute, conn, login_cookies)
        
def time_rename_profile(number, username, password, uuid, login_cookies = None):
    """Attempts to gauge how long it will take for a round trip of renaming a profile via
    Mojang's (obscured) API. This will send a number of requests to the URL with dummy
    data. The username and password are required to login if login_cookies is None.

    Note that this will not actually rename the profile; instead, dummy data is passed:
    the password is blank and the username is 'Notch'.

    Keyword arguments:
    number -- Number of fake requests to send
    username -- Username of Mojang account (only required if login_cookies is None)
    password -- Password of Mojang account (only required if login_cookies is None)
    uuid -- UUID of Minecraft account that will be renamed
    login_cookies -- Existing login_cookies (see mojang#get_cookies)

    Returns the average round-trip time to rename a profile, or 0 if something failed
    (e.g. could not connect, could not login)
    """
    
    if number <= 0:
        return 0

    # Login if necessary
    if not login_cookies:
        result = login(username, password)
        if not result \
        or result[0] != 200 and result[0] != 302 \
        or len([ header for header in result[1] if header[0].lower() == 'location' and header[1].lower()[-6:] == URL_LOGIN.path ]) > 0:
            print(result)
            return 0

        login_cookies = get_cookies(result[1])

    total = 0

    # Send fake logins `number` times
    for i in range(number):
        # Generate request (not timed)
        (fake_rename, conn, _) = rename_profile_later(username, '', uuid, 'Notch', login_cookies)

        # Start timing and execute
        before = time.perf_counter()
        fake_rename(conn)
        after = time.perf_counter()
        
        total += (after - before)

    return total / number
