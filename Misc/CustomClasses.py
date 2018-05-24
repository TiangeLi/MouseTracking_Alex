# coding=utf-8

"""Usefl reimplementations of many classes"""

import time
import numpy as np
import multiprocessing as mp


class StoppableProcess(mp.Process):
    """Multiprocessing Process with stop() method"""
    def __init__(self):
        super(StoppableProcess, self).__init__()
        self.daemon = True
        # We can check the self._stop flag to determine if running or not
        self._stop = mp.Event()

    def stop(self):
        """Sets the STOP flag"""
        self._stop.set()

    def stopped(self):
        """Checks status of STOP flag"""
        return self._stop.is_set()


# Timing Classes
class StopWatch(object):
    """A timing object with start, pause, and summation functions"""
    def __init__(self):
        self.start_timer = None
        self.total_time = 0
        self.started = False

    def start(self):
        """Starts the stopwatch"""
        self.started = True
        self.start_timer = time.perf_counter()

    def stop(self):
        """Stop counting time, add elapsed to summed time"""
        self.total_time += time.perf_counter() - self.start_timer
        self.start_timer = None
        self.started = False

    def elapsed(self):
        """Return total time elapsed, including any from current timer"""
        if self.started:
            elapsed = time.perf_counter() - self.start_timer
            return self.total_time + elapsed
        return self.total_time

    def reset(self):
        """Resets total time"""
        self.total_time = 0
        self.start_timer = None
        self.started = False


# Multiprocessing Message Functions
class ProcessMessage(object):
    """A Message Container"""
    def __init__(self, device, command, value):
        self.device = device
        self.command = command
        self.value = value


def NewMessage(dev=None, cmd=None, val=None):
    """Returns a Packaged ProcessMessage Tuple"""
    msg = ProcessMessage(device=dev, command=cmd, value=val)
    return msg.device, msg.command, msg.value


def ReadMessage(process_message_tuple):
    """Converts a packaged ProcessMessage tuple into a ProcessMessage object"""
    return ProcessMessage(*process_message_tuple)
