import time
import datetime
import digitalocean
import quickscope.mojang
import quickscope.app
import quickscope.timing

# Commands to be executed on Droplet spawn
USER_DATA = """#!/bin/bash
scl enable python33 -- quickscope -u {username} -p {password} {target} {uuid} slave -c {variance} {expiry} >> /home/quickscope.log"""

# How long before the username becomes available to create droplets & run worker tasks
DROPLET_PREP_TIME = 30 * 60 # 30 mins

# How long after the username becomes available to kill droplets
DROPLET_KILL_TIME = 10 * 60 # 10 mins

def start(args, username, password, api_key):
    
    expiry = quickscope.mojang.get_free_time(args.target)
    
    # Ensure we can get the name
    if expiry is None:
        print('Cannot quickscope this username -- it is taken!')
        return

    # Calculate time at which to start prep
    available = expiry + quickscope.app.USERNAME_HOLDING_TIME
    when = available - DROPLET_PREP_TIME
    remaining = when - time.time()

    if remaining < 0:
        if available - time.time() < 0:
            print('Too late to quickscope! Username already expired')
            return
        else:
            # If we don't have the time we'd like to have to prep, but
            # the username is still approaching the 'available' window,
            # execute immediately
            print('Not enough time to have comfortable droplet prep; prepping anyway.')
            remaining = 0

    # Start timer to start prep
    print('Started timer to create droplets; timer will execute {}s after now ({})'.format(remaining, datetime.datetime.now().isoformat()))
    create_timer = quickscope.timing.PreciseTimer(remaining, lambda: _create_droplets(args, username, password, api_key, expiry))
    create_timer.start()

def _create_droplets(args, username, password, api_key, expiry):
    droplets = []
    available = expiry + quickscope.app.USERNAME_HOLDING_TIME

    print('Beginning droplet creation...')
    
    # Create each droplet
    for i in range(args.droplets):
        variance = args.variances[i % len(args.variances)]
        print('Creating droplet {} (variance: {})...'.format(i, variance))
        droplet = digitalocean.Droplet(token=api_key,
                                       name='qs-sl-{}'.format(i),
                                       region='ams2',
                                       image=args.snapshot,
                                       size_slug='512mb',
                                       backups=False,
                                       user_data=USER_DATA.format(
                                           username=username,
                                           password=password,
                                           target=args.target,
                                           uuid=args.uuid,
                                           variance=variance,
                                           expiry=expiry
                                        ))
        droplet.create()
        droplets.append(droplet)


    print('Droplets created. Waiting to kill them...')
        
    # ... and then schedule to kill them all
    when = available + DROPLET_KILL_TIME
    remaining = when - time.time()

    if remaining < 0:
        remaining = 0

    print('Started timer to kill droplets')
    destroy_timer = quickscope.timing.PreciseTimer(remaining, lambda: _destroy_droplets(droplets))
    destroy_timer.start()

def _destroy_droplets(droplets):
    print('Beginning droplet destruction...')
    for droplet in droplets:
        droplet.destroy()
    print('Droplet destruction initiated!')
