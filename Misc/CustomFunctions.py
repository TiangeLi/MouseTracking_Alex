# coding=utf-8

"""Functions for commonly performed tasks"""

import os
from datetime import datetime
from Misc.GlobalVars import *


def format_secs(time_in_secs, option='norm'):
    """Turns seconds into various time formats"""
    output = ''
    # check option given is in correct list of options
    if option not in ['norm', 'with_ms', MINS, SECS]:
        raise ValueError('[{}] is not a valid option!'.format(option))
    # Obtain mins, secs, millis
    m = int(time_in_secs) // 60
    s = int(time_in_secs) % 60
    millis = int((time_in_secs - int(time_in_secs)) * 1000)
    # Report time in format specified
    if option == 'norm':  # MM:SS
        output = '{:0>2}:{:0>2}'.format(m, s)
    elif option == 'with_ms':  # MM:SS.mss
        output = '{:0>2}:{:0>2}.{:0>3}'.format(m, s, millis)
    elif option == MINS:  # MM
        output = '{:0>2}'.format(m)
    elif option == SECS:  # SS
        output = '{:0>2}'.format(s)
    # Finish
    return output


def format_daytime(option, use_as_save, dayformat='/', timeformat=':'):
    """Returns Day and Time in various formats
    option = day, time, daytime
    use_as_save: True, False
    """
    time_now = datetime.now()
    # Check option given is a valid option
    if option not in [DAY, TIME, DAY+TIME]:
        raise ValueError('[{}] is not a valid option!'.format(option))
    # If use_as_save, force format = '-'
    dayformat, timeformat = ('-', '-') if use_as_save else (dayformat, timeformat)
    # Output final formatted day and time
    formatted_day = '{:0>4}{}{:0>2}{}{:0>2}'.format(time_now.year, dayformat,
                                                    time_now.month, dayformat,
                                                    time_now.day)
    formatted_time = '{:0>2}{}{:0>2}{}{:0>2}'.format(time_now.hour, timeformat,
                                                     time_now.minute, timeformat,
                                                     time_now.second)
    # Report
    if option == DAY: return formatted_day
    elif option == TIME: return formatted_time
    elif option == DAY+TIME: return '{}_{}'.format(formatted_day, formatted_time)


def clear_console():
    """Clears the command console"""
    os.system('cls' if os.name == 'nt' else 'clear')
