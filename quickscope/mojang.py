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
    cookie_headers = [ header[1] for header in headers if header[0].lower() == 'set-cookie' ]
    cookie_jar     = http.cookies.SimpleCookie()
    for h in cookie_headers:
        cookie_jar.load(h)
    return cookie_jar

def get_login_error(result):
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
    
    # Login if needed to
    if login_cookies is None:

        # Attempt login
        result = login(username, password)

        # Handle errors
        error = get_login_error(result)
        if error is not None:
            return (False, error, None)

        """
        if not result: # Failure to get auth token if result is none
            return (False, 'Failed to get authenticity token', None)
        elif result[0] != 200 and result[0] != 302: # Some failure if wrong response code
            print(type(result[0]))
            return (False, 'Unrecognized response code: {}'.format(result[0]), None)
        elif len([ header for header in result[1] if header[0].lower() == 'location' and header[1].lower()[-6:] == URL_LOGIN.path ]) > 0: # Incorrect login if redirecting to /login
            return (False, 'Incorrect login', None)
    """
        
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
    if number <= 0:
        return

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
    
# [debug]
#print(login('daviga404+test@gmail.com', 'Memes are the foundation of the soul.'))
"""
print("timing...")
time = time_rename_profile(20, 'daviga404+dynamited3@gmail.com', '', 'c7360a33376042018089e50262e304cb')
print("average time: {}ms".format(time * 1000))
#(future, conn, login_cookies) = rename_profile_later('daviga404+dynamited3@gmail.com', '', 'c7360a33376042018089e50262e304cb', 'kek')
"""
"""
if future == False:
    print('Failed: {}'.format(conn))
else:
    input("press something to continue")
    before = time.perf_counter()
    future(conn)
    after = time.perf_counter()
    print('Took {}ms'.format((after - before) * 1000))
"""

"""

(status, headers, body) = login('daviga404+dynamited3@gmail.com', '')
login_cookies = get_cookies(headers)

(status, headers) = api_get_rename_profile('c7360a33376042018089e50262e304cb', login_cookies)
at = get_authenticity_token(headers)

before = time.perf_counter()
conn = create_connection(URL_RENAME_PROFILE)
#print('create_connection: {}s'.format(time.perf_counter() - before))

time.sleep(25)

conn.request('POST', URL_RENAME_PROFILE.path.format(uuid='c7360a33376042018089e50262e304cb'), urllib.parse.urlencode({
    'newName': 'bob',
    'password': '',
    'authenticityToken': at
}),
{
    'User-Agent': USER_AGENT,
    'Accept-Encoding': 'gzip, deflate',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Cookie': get_cookies(headers).output(attrs=[], header='', sep='; ')
})

print('request: {}ms'.format((time.perf_counter() - before) * 1000))

#resp = conn.getresponse()
"""
"""
print(resp.getheaders())
print(resp.status)6
print(resp.read())
"""
"""
cookie_headers = [ header[1] for header in headers if header[0].lower() == 'set-cookie' ]
cookie_jar = http.cookies.SimpleCookie()
for cookie in cookie_headers:
    cookie_jar.load(cookie)76


cookiess = [ header[1] for header in headers if header[0].lower() == 'set-cookie' ]
testco = ','.join(cookiess)
at_cookies = [ cookie for cookie in cookiess if cookie[:12].lower() == 'play_session' ]
c = cookies.SimpleCookie()
c.load(cookiess[0])
c.load(cookiess[1])
print(c)"""
