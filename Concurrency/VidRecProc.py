# coding=utf-8

"""Process for recording videos to file"""

import cv2
import sys
import time
import numpy as np
import threading as thr
import multiprocessing as mp
from Misc.CustomClasses import StoppableProcess, ReadMessage, NewMessage
from Misc.GlobalVars import *
if sys.version[0] == '2':
    import Queue as Queue
else:
    import queue as Queue


class VideoRecorder(StoppableProcess):
    """Has a view to a provided; records from them"""
    def __init__(self, name, is_color, file_name_ending, mp_array, recording_sync):
        super(VideoRecorder, self).__init__()
        self.name = name
        self.is_color = is_color
        self.connected = True
        self.output_dimensions = VID_DIM[1], VID_DIM[0]
        # Cross process communication
        self.output_msgs = PROC_HANDLER_QUEUE
        self.exp_start_event = EXP_START_EVENT
        self.input_msgs = mp.Queue()
        self.parent_pipe, self.pipe = mp.Pipe()
        # Recording params
        self.file_name_ending = file_name_ending
        self._recording = False
        self._ttl_num_frames = -1
        self.curr_frame = 0
        self.frame_buffer = None
        # Shared MP arrays
        self.mp_array = mp_array
        # Rec Sync Event
        self.rec_sync = recording_sync

    # Initialize objects
    def init_unpickleable_objs(self):
        """Creates objects that must exist in the new process"""
        # Numpy views of shared mp array
        self.image_array = self.mp_array.generate_np_array()
        # Msg parser
        self.setup_msg_parser()
        # Video buffers
        self.frame_buffer = Queue.Queue()

    def setup_msg_parser(self):
        """Dictionary of {Msg:Actions}"""
        self._msg_parser = {
            CMD_START: lambda params: self.set_record_to_file(record=True, recording_params=params),
            CMD_STOP: lambda val: self.set_record_to_file(record=False, recording_params=None),
            CMD_EXIT: lambda val: self.stop()
        }

    # Msg polling and processing thread
    def msg_proc_handler(self, cmd):
        """Sends a message to process handler"""
        msg = NewMessage(dev=self.name, cmd=cmd)
        self.output_msgs.put_nowait(msg)

    def process_message(self, msg):
        self._msg_parser[msg.command](msg.value)

    def msg_polling(self):
        """Run on separate thread. Listens to input_msgs queue for messages"""
        while self.connected:
            try:
                msg = self.input_msgs.get(timeout=0.5)
            except Queue.Empty:
                time.sleep(30.0 / 1000.0)
            else:
                msg = ReadMessage(msg)
                self.process_message(msg)

    def video_writing_worker(self):
        """a worker thread to write frames"""
        record = True
        while self.connected and record:
            try:
                img = self.frame_buffer.get(timeout=0.1)
            except Queue.Empty:
                if not self._recording:
                    record = False
                else:
                    time.sleep(1.0 / 1000.0)
            else:
                self._video_writer.write(img)
        self._video_writer.release()
        self.msg_proc_handler(cmd=MSG_VIDREC_FINISHED)
        print('Closing FrameWriter ({})...'.format(self.name))

    def set_record_to_file(self, record, recording_params):
        """Sets recording state and save file name"""
        if record:
            fname = recording_params[0]
            duration = recording_params[1]
            # Total frames to record at CAMERA_FRAMERATE
            self._ttl_num_frames = int(duration * CAMERA_FRAMERATE)
            # setup video recorders
            self._video_writer = cv2.VideoWriter(fname + self.file_name_ending,
                                                 cv2.VideoWriter_fourcc(*'XVID'), CAMERA_FRAMERATE,
                                                 self.output_dimensions, self.is_color)
            # Create worker thread
            self.frame_buffer.queue.clear()
            worker = thr.Thread(target=self.video_writing_worker, name='video_writer', daemon=True)
            # Let proc_handler know we're setup and wait until other processes are ready
            self.pipe.send(MSG_RECEIVED)
            self.exp_start_event.wait()
            self._recording = True
            worker.start()
        elif not record:
            self._ttl_num_frames = -1

    # Main thread
    def run(self):
        """Called by start() when spawning a new process"""
        self.init_unpickleable_objs()
        # Threading
        POLLING = 'polling'
        thr_msg_polling = thr.Thread(target=self.msg_polling, name=POLLING, daemon=True)
        thr_msg_polling.start()
        # Main Process Loop
        while self.connected:
            self.record_to_file()
            if self.stopped():
                self.connected = False
                while True:
                    time.sleep(5.0 / 1000.0)
                    threads = [thread.name for thread in thr.enumerate()]
                    if POLLING not in threads and 'video_writer' not in threads:
                        break
        print('Exiting ({}) Video Recorder...'.format(self.name))

    def record_to_file(self):
        """Records images from all mp_arrays to file"""
        if not self._recording:
            time.sleep(5.0 / 1000.0)
            return
        if self.curr_frame <= self._ttl_num_frames:
            if self.rec_sync.is_set():
                frame = self.get_output_img()
                self.frame_buffer.put_nowait(frame)
                self.rec_sync.clear()
                self.curr_frame += 1
            else:
                time.sleep(1.0 / 1000.0)
        elif self.curr_frame > self._ttl_num_frames:
            self._recording = False
            self.curr_frame = 0
            self.msg_proc_handler(cmd=MSG_VIDREC_SAVING)

    def get_output_img(self):
        """Gets output image to save"""
        return self.image_array


class CV2VideoRecorder(VideoRecorder):
    """Has a view to a provided; records from them. Subclasses VideoRecorder"""
    def __init__(self, name, is_color, file_name_ending, recording_sync, cv2gui, pathing, heatmap, gradient, progbar):
        super(CV2VideoRecorder, self).__init__(name=name, is_color=is_color,
                                               file_name_ending=file_name_ending,
                                               recording_sync=recording_sync, mp_array=None)
        self.output_dimensions = VID_DIM_RGB[1] + MAP_DIMS[1], VID_DIM_RGB[0] + GRADIENT_HEIGHT
        # Shared MP arrays
        self.cv2gui = cv2gui
        self.pathing = pathing
        self.heatmap = heatmap
        self.gradient = gradient
        self.progbar = progbar

    # Initialize objects
    def init_unpickleable_objs(self):
        """Creates objects that must exist in the new process"""
        # Numpy views of shared mp array
        self.cv2gui = self.cv2gui.generate_np_array()
        self.pathing = self.pathing.generate_np_array()
        self.heatmap = self.heatmap.generate_np_array()
        self.gradient = self.gradient.generate_np_array()
        self.progbar = self.progbar.generate_np_array()
        np_array_shape = self.output_dimensions[1], self.output_dimensions[0], 3
        self.image = np.zeros(np_array_shape, dtype='uint8')
        self.cv2gui_slice = self.image[:VID_DIM_RGB[0], MAP_DIMS[1]:np_array_shape[1], :]
        self.pathing_slice = self.image[:MAP_DIMS[0], :MAP_DIMS[1], :]
        self.heatmap_slice = self.image[MAP_DIMS[0]:VID_DIM_RGB[0], :MAP_DIMS[1], :]
        self.gradient_slice = self.image[VID_DIM_RGB[0]:np_array_shape[0], :MAP_DIMS[1], :]
        self.progbar_slice = self.image[VID_DIM_RGB[0]+1:np_array_shape[0]-1, MAP_DIMS[1]:np_array_shape[1], :]
        # Msg parser
        self.setup_msg_parser()
        # Video buffers
        self.frame_buffer = Queue.Queue()

    # Main thread
    def get_output_img(self):
        self.heatmap_slice[:] = self.heatmap
        self.pathing_slice[:] = self.pathing
        self.cv2gui_slice[:] = self.cv2gui
        self.gradient_slice[:] = self.gradient
        self.progbar_slice[:] = self.progbar
        return self.image[..., ::-1]
