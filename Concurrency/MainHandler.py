# coding=utf-8

"""Main Process Handler managing communication from GUI to all child processes"""

import cv2
import sys
import time
import multiprocessing as mp
from Misc.GlobalVars import *
from Misc.CustomClasses import *
if sys.version[0] == '2':
    import Queue as Queue
else:
    import queue as Queue


class ProcessHandler(StoppableProcess):
    """Main handler class with communication protocols to child processes"""
    def __init__(self, cmr_msgs, cv2_msgs, coords_msgs, cv2_vidrec_msgs, cmr_vidrec_msgs, *msg_rcvd_pipes):
        super(ProcessHandler, self).__init__()
        self.input_msgs = PROC_HANDLER_QUEUE
        self.exp_start_event = EXP_START_EVENT
        self.msg_rcvd_pipes = msg_rcvd_pipes
        self.vidrec_saving_list = []
        self.vidrec_finished_list = []
        self.cv2_bg_w_boundary, self.cv2_bg_original = None, None
        self.queue_selector = {
            PROC_CMR: cmr_msgs,
            PROC_CV2: cv2_msgs,
            PROC_COORDS: coords_msgs,
            PROC_CV2_VIDREC: cv2_vidrec_msgs,
            PROC_CMR_VIDREC: cmr_vidrec_msgs,
            PROC_GUI: MASTER_DUMP_QUEUE
        }

    def setup_msg_parser(self):
        """Dictionary of {Msg:Actions}"""
        self.msg_parser = {
            # Messages with general destinations
            MSG_ERROR: lambda dev, destination: self.send_message(targets=(destination,), cmd=MSG_ERROR),
            CMD_START: lambda dev, name: self.run_experiment(run=True, trial_params=name),
            CMD_STOP: lambda dev, val: self.run_experiment(run=False),
            CMD_SET_TIME: lambda dev, ttl_time: self.send_message(targets=(PROC_COORDS,),
                                                                  cmd=CMD_SET_TIME, val=ttl_time),
            CMD_EXIT: lambda d, v: self.close_children(),
            # Messages bound for CV2 Process
            CMD_SET_BOUNDS: lambda dev, bounds: self.send_message(targets=(PROC_CV2,), cmd=CMD_SET_BOUNDS, val=bounds),
            CMD_SHOW_TRACKED: lambda dev, val: self.send_message(targets=(PROC_CV2,), cmd=CMD_SHOW_TRACKED),
            CMD_GET_BG: lambda dev, val: self.send_message(targets=(PROC_CV2,), cmd=CMD_GET_BG),
            CMD_TARG_DRAW: lambda dev, targ_area: self.send_message(targets=(PROC_CV2, PROC_COORDS),
                                                                    cmd=CMD_TARG_DRAW, val=targ_area),
            CMD_TARG_RADIUS: lambda dev, radius: self.send_message(targets=(PROC_CV2, PROC_COORDS),
                                                                   cmd=CMD_TARG_RADIUS, val=radius),
            # Messages bound for Camera Process
            CMD_SET_VIDSRC: lambda dev, fname: self.send_message(targets=(PROC_CMR,), cmd=CMD_SET_VIDSRC, val=fname),
            # Messages bound for Coords Process
            CMD_CLR_MAPS: lambda dev, val: self.send_message(targets=(PROC_COORDS,), cmd=CMD_CLR_MAPS),
            CMD_TOGGLE_MANUAL_TRIGGER: lambda d, v: self.send_message(targets=(PROC_COORDS,),
                                                                      cmd=CMD_TOGGLE_MANUAL_TRIGGER),
            CMD_SEND_STIMULUS: lambda d, v: self.send_message(targets=(PROC_COORDS,), cmd=CMD_SEND_STIMULUS),
            # Messages bound for GUI
            MSG_VIDREC_SAVING: lambda proc_origin, val: self.vidrec_saving(saving=True, proc_origin=proc_origin),
            MSG_VIDREC_FINISHED: lambda proc_origin, val: self.vidrec_saving(saving=False, proc_origin=proc_origin),
            # Messages intended for Proc Handler
            CMD_NEW_BACKGROUND: lambda dev, new_backgrounds: self.save_backgrounds(new_backgrounds),
        }

    def process_message(self, msg):
        """Follows instructions in queue message"""
        self.msg_parser[msg.command](msg.device, msg.value)

    def send_message(self, targets, cmd=None, val=None):
        """Sends a message to children"""
        msg = NewMessage(cmd=cmd, val=val)
        for target in targets:
            self.queue_selector[target].put_nowait(msg)

    def run(self):
        """Called by start(), spawns new process"""
        self.setup_msg_parser()
        while not self.stopped():
            try:
                msg = self.input_msgs.get(timeout=0.5)
            except Queue.Empty:
                time.sleep(1.0 / 1000.0)
            else:
                msg = ReadMessage(msg)
                self.process_message(msg)
        print('Exiting Process Handler...')

    def close_children(self):
        """Close all child processes before exiting"""
        self.send_message(targets=(PROC_CMR, PROC_CV2, PROC_COORDS,
                                   PROC_CV2_VIDREC, PROC_CMR_VIDREC),
                          cmd=CMD_EXIT)
        self.stop()

    # Experiment running functions
    def run_experiment(self, run, trial_params=None):
        """Tells child widgets to start/stop experiment"""
        # Start
        if run:
            self.exp_start_event.clear()
            quality = int(cv2.IMWRITE_PNG_COMPRESSION), 0
            cv2.imwrite('{}_bg_w_bounds.png'.format(trial_params[0]), self.cv2_bg_w_boundary, quality)
            cv2.imwrite('{}_bg_original.png'.format(trial_params[0]), self.cv2_bg_original, quality)
            self.send_message(targets=(PROC_COORDS, PROC_CV2_VIDREC, PROC_CMR_VIDREC),
                              cmd=CMD_START,
                              val=trial_params)
            for pipe in self.msg_rcvd_pipes:
                pipe.recv()
            # don't allow any process to proceed unless all processes have confirmed receipt of message
            self.exp_start_event.set()
            # Once exp_start_event is set, we can let master gui know that we've begun recording/etc.
            self.send_message(targets=(PROC_GUI,), cmd=MSG_STARTED)
        # Forced stop
        elif not run:
            self.exp_start_event.clear()
            self.send_message(targets=(PROC_COORDS, PROC_CV2_VIDREC, PROC_CMR_VIDREC),
                              cmd=CMD_STOP)

    def save_backgrounds(self, new_backgrounds):
        """Saves backgrounds from cv2_proc for output into file"""
        self.cv2_bg_w_boundary, self.cv2_bg_original = new_backgrounds

    def vidrec_saving(self, saving, proc_origin):
        """collects all CMD_VIDREC_SAVING and CMD_VIDREC_SAVED signals, then sends a single signal
        to GUI when all signals are collected"""
        if saving:
            self.vidrec_saving_list.append(proc_origin)
            if PROC_CV2_VIDREC in self.vidrec_saving_list\
                    and PROC_CMR_VIDREC in self.vidrec_saving_list\
                    and PROC_COORDS in self.vidrec_saving_list:
                self.vidrec_saving_list = []
                self.send_message(targets=(PROC_GUI,), cmd=MSG_VIDREC_SAVING)
        elif not saving:
            self.vidrec_finished_list.append(proc_origin)
            if PROC_CV2_VIDREC in self.vidrec_finished_list\
                    and PROC_CMR_VIDREC in self.vidrec_finished_list\
                    and PROC_COORDS in self.vidrec_finished_list:
                self.vidrec_finished_list = []
                self.send_message(targets=(PROC_GUI,), cmd=MSG_VIDREC_FINISHED)
