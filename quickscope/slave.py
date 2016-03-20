from threading import Thread
import time
import quickscope.mojang
import quickscope.timing
import quickscope.app

# Maximum number of login attempts
RETRY_LIMIT = 5

# Latency check accuracy
LATENCY_CHECK_ACCURACY = 10

debugkek = 0

def start(args, username, password, retries = 0):
    global debugkek
    
    available = args.expiry + quickscope.app.USERNAME_HOLDING_TIME
#    remaining = available - time.time()

    # Try to login
    login_result = quickscope.mojang.login(username, password)
    login_error = quickscope.mojang.get_login_error(login_result)

    if login_error is not None:
        if retries < RETRY_LIMIT:
            return start(args, username, password, retries + 1)
        else:
            print('Error: failed to login after {} attempts. Latest error message: {}'.format(RETRY_LIMIT, login_error))
            return

    # Store login cookies
    login_cookies = quickscope.mojang.get_cookies(login_result[1])
    
    # Get the latency to Mojang server
    latency = quickscope.mojang.time_rename_profile(LATENCY_CHECK_ACCURACY, username, password, args.uuid, login_cookies)
    variance = args.variance / 1000
    interval = args.interval / 1000

    print('Latency: {}'.format(latency))
    debugkek = available

    # SEND THE BATTLESHIPS TO BATTLE fdsjnkhgnslhdfsk
    for request in range(args.requests):
        when = available - latency + variance + interval * request
        thread = SnipeThread(when, username, password, args.uuid, args.target, login_cookies)
        thread.start()


class SnipeThread(Thread):

    PREPARE_TIME = 60

    def __init__(self, when, username, password, uuid, new_name, login_cookies):
        Thread.__init__(self)
        self.when = when
        self.username = username
        self.password = password
        self.uuid = uuid
        self.new_name = new_name
        self.login_cookies = login_cookies

    def run(self):
        difference = self.when - self.PREPARE_TIME - time.time()
        if difference < 0:
            print('Snipe not run, difference < 0.')
            return
        
        timer = quickscope.timing.PreciseTimer(difference, lambda: self.prepare())
        timer.start()

    def prepare(self):
        # Prepare the battleships/request!
        (execute, conn, _) = quickscope.mojang.rename_profile_later(self.username, self.password, self.uuid, self.new_name, self.login_cookies)

        # Oh shit, something might have went wrong
        if execute == False:
            print('Fuck! {}'.format(conn))
            return

        # Right, we're ready! START THE TIMERRRRRRRRRRR
        difference = self.when - time.time()
        timer = quickscope.timing.PreciseTimer(difference, lambda: self.attack(execute, conn))
        timer.start()

    def attack(self, execute, conn):
        before = time.perf_counter()
        execute(conn)
        elapsed = time.perf_counter() - before
        
        afterdubcek = (time.time() - debugkek) * 1000
        
        resp = conn.getresponse()
        print('Attack succeeded! Status: {}; body: {}. Executed {}ms (vs {}ms); took {}; '.format(resp.status, str(resp.read()), afterdubcek, (self.when - debugkek) * 1000, elapsed * 1000))
        
