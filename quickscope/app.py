import argparse
import os

import quickscope.mojang
import quickscope.slave
import quickscope.master

# Environment variables
ENV_MOJANG_EMAIL = 'MOJANG_EMAIL'
ENV_MOJANG_PASS = 'MOJANG_PASS'
ENV_DO_KEY = 'DO_KEY'

# Seconds that a username is held by Mojang for after 'expiry' (37 days)
USERNAME_HOLDING_TIME = 37 * 24 * 60 * 60

def int_range(lower, upper):
    def validator(string):
        value = 0
        try:
            value = int(string)
            if value < lower or value > upper:
                raise argparse.ArgumentTypeError('\'{}\' is outside the range {}-{}'.format(value, lower, upper))
        except ValueError:
            raise argparse.ArgumentTypeError('invalid int value: \'{}\''.format(string))
        else:
            return value
    return validator

def int_list(string):
    ints = []
    for part in string.split(','):
        try:
            value = int(part.strip())
            ints.append(value)
        except ValueError:
            raise argparse.ArgumentTypeError('invalid int value: \'{}\''.format(part))
    return ints
            

def start():
    parser = argparse.ArgumentParser(description='Snipes OG Minecraft usernames')
    parser.add_argument('target', help='username of Minecraft account to snipe')
    parser.add_argument('uuid', help='UUID of Minecraft account associated with Mojang account')
    parser.add_argument('-u', '--username', help='username (email) of Mojang account to use; if not set, use the environment variable MOJANG_EMAIL')
    parser.add_argument('-p', '--password', help='password of Mojang account to use; if not set, use the environment variable MOJANG_PASS')
    
    subparsers = parser.add_subparsers(dest='mode')

    # Define arguments for slave mode
    slave_parser = subparsers.add_parser('slave', help='slave mode')
    slave_parser.add_argument('expiry', type=int, help='UNIX timestamp (seconds) of when username \'expired\' (required)')
    slave_parser.add_argument('-c', '--variance', type=int, default=0, help='variance in milliseconds for when to send the request; can be negative (default: 0)')
    slave_parser.add_argument('-r', '--requests', type=int, default=5, help='number of requests to send with INTERVAL between them, starting at EXPIRY - latency + VARIANCE + INTERVAL * i (default: 5)')
    slave_parser.add_argument('-i', '--interval', type=int, default=20, help='interval in milliseconds between each request. (default: 20)')

    # Define arguments for master mode
    master_parser = subparsers.add_parser('master', help='master mode')
    master_parser.add_argument('-s', '--snapshot', type=int, help='snapshot ID to use to spawn droplets from', required=True)
    master_parser.add_argument('-d', '--droplets', type=int_range(1, 25), help='number of droplets to spawn (default: 5, maximum: 25)', default=5)
    master_parser.add_argument('-k', '--api-key', help='DigitalOcean API key; if not set, use the environment variable DO_KEY')
    master_parser.add_argument('-c', '--variances', type=int, nargs='+', default=[0], help='comma-separated list of variances for each droplet (default: 0 for all)')

    args = parser.parse_args()
    
    username = args.username if args.username else os.getenv(ENV_MOJANG_EMAIL)
    password = args.password if args.password else os.getenv(ENV_MOJANG_PASS)
    api_key = args.api_key if args.api_key else os.getenv(ENV_DO_KEY)

    # Ensure we have a Mojang username 
    if not username or not password:
        print('error: missing Mojang username/password')
        parser.print_help()
        return

    # Ensure we have a DO key if in master mode
    if args.mode == 'master' and not api_key:
        print('error: missing DigitalOcean API key')
        parser.print_help()
        return

    # Call appropriate start routine
    if args.mode == 'slave':
        quickscope.slave.start(args, username, password)
    elif args.mode == 'master':
        quickscope.master.start(args, username, password, api_key)
    else:
        print('error: missing mode')
        parser.print_help()

def start_master(args, username, password):
    print('Checking remaining time until \'{}\' becomes free...'.format(username))
    expiry = quickscope.mojang.get_free_time(args.target)

    if expiry is None:
        print('Error: username is not free.')
    
