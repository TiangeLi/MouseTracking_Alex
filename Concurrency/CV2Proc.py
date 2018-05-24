# coding=utf-8

"""CV2 Operations. Returns processed image and mouse coordinates"""

import sys
import cv2
import time
import numpy as np
import threading as thr
import multiprocessing as mp
from collections import deque
from GUI.DataDisplays.SendRecvProtocols import SyncableMPArray
from Misc.CustomClasses import *
from Misc.GlobalVars import *
if sys.version[0] == '2':
    import Queue as Queue
else:
    import queue as Queue


class CV2TargetAreaPerimeter(object):
    """Container for target area perimeter information"""
    def __init__(self):
        self.draw = False
        self.norm_x = None
        self.norm_y = None
        self.x = None
        self.y = None
        self.radius = None

    def toggle_draw(self, params):
        """Update params and toggle draw or not draw"""
        if params:
            self.draw = True
            (self.x, self.y), (self.norm_x, self.norm_y), self.radius = params
        else:
            self.draw = False

    def update_radius(self, radius):
        """Sets new radius"""
        self.radius = radius


class CV2Processor(StoppableProcess):
    """CV2 Operations on supplied image"""
    def __init__(self, saved_bounds):
        super(CV2Processor, self).__init__()
        self.name = PROC_CV2
        self.connected = True
        self.rec_to_file_sync_event = mp.Event()
        # Communication
        self.input_msgs = mp.Queue()
        self.output_msgs = PROC_HANDLER_QUEUE
        # Input and Outputs
        self.cmrcv2_mp_array = SyncableMPArray(VID_DIM)
        self.cv2gui_mp_array = SyncableMPArray(VID_DIM_RGB)
        self.coords_output_queue = mp.Queue()
        self.reset_coords_output = False
        # Image Tracking Params
        self.has_background = False
        self.bounding_coords = [] if saved_bounds == DEFAULT_BOUNDS else saved_bounds
        self.show_only_tracked_space = False
        self.contrail_coords = deque(maxlen=32)
        # CV2 Params
        self.num_calib_frames = 20
        self.accum_fn = np.mean
        self.thresh = -30
        self.tracking_size = 350.0
        self.opening_radius = 4
        # Init CV2 drawn objects
        self.targ_perim = None

    def init_unpickleable_objs(self):
        """Setup objects that must be initialized in running process"""
        self.setup_msg_parser()
        self.setup_error_img()
        self.input_array = self.cmrcv2_mp_array.generate_np_array()
        self.output_array = self.cv2gui_mp_array.generate_np_array()
        self.targ_perim = CV2TargetAreaPerimeter()
        self.frame_buffer = Queue.Queue()

    def run(self):
        """called by start(); spawns new process"""
        self.init_unpickleable_objs()
        self.get_kernel()
        # Threads
        POLLING, SEND_FRAMES = 'polling', 'send_frames'
        thr_send_frames = thr.Thread(target=self.submit_frame, name=SEND_FRAMES, daemon=True)
        thr_polling = thr.Thread(target=self.msg_polling, name=POLLING, daemon=True)
        thr_send_frames.start()
        thr_polling.start()
        # Main loop
        while self.connected:
            self.acquire_background()
            self.get_frames()
            # Once we get a new background, it is necessary to reset the heatmaps and pathing maps
            if self.reset_coords_output:
                self.reset_coords_output = False
                self.msg_proc_handler(cmd=CMD_CLR_MAPS)
            # Check if exiting process
            if self.stopped():
                self.connected = False
                while True:
                    time.sleep(5.0 / 1000.0)
                    threads = [thread.name for thread in thr.enumerate()]
                    threads_closed = (SEND_FRAMES not in threads, POLLING not in threads)
                    if all(threads_closed):
                        break
        print('Exiting CV2 Processor...')

    def submit_frame(self):
        """Polls for frames and sends to output np array"""
        while self.connected:
            if self.output_array.can_send_img():
                data = self.frame_buffer.get()
                self.output_array.send_img(data)
                self.output_array.set_can_recv_img()
                # Inform CV2VidRecProcess that it can record a frame
                self.rec_to_file_sync_event.set()
            else:
                time.sleep(1.0 / 1000.0)

    # Msging Protocol
    def setup_msg_parser(self):
        """Dictionary of {Msg:Actions}"""
        self.msg_parser = {
            CMD_EXIT: lambda val: self.stop(),
            CMD_SET_BOUNDS: lambda val: self.recv_new_bounds(val),
            CMD_SHOW_TRACKED: lambda val: self.toggle_show_cropped_img(),
            CMD_GET_BG: lambda val: self.get_new_bg(),
            CMD_TARG_DRAW: lambda params: self.targ_perim.toggle_draw(params),
            CMD_TARG_RADIUS: lambda radius: self.targ_perim.update_radius(radius),
            MSG_ERROR: lambda val: self.display_error_img()
        }

    def process_message(self, msg):
        """Follows instructions in queue message"""
        self.msg_parser[msg.command](msg.value)

    def msg_proc_handler(self, cmd, val=None):
        """Sends a message to process handler"""
        msg = NewMessage(dev=self.name, cmd=cmd, val=val)
        self.output_msgs.put_nowait(msg)

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

    # Acquire Images
    def image_iterator(self):
        """Yields new frame when ready"""
        return self.input_array.copy()

    def get_frames(self):
        """Acquire one image per call"""
        if self.input_array.can_recv_img():
            frame = self.image_iterator()
            frame, coord = self.track_mouse(frame=frame)
            if coord != (None, None):
                frame = self.process_coords(frame, coord)
            self.frame_buffer.put_nowait(frame)
            self.coords_output_queue.put_nowait(coord)
            self.input_array.set_can_send_img()
        else:
            time.sleep(1.0 / 1000.0)

    # CV2 Processing
    def get_new_bg(self):
        """Gets new background image"""
        self.has_background = False

    def acquire_background(self):
        """Gets background to compare mouse motion against"""
        if not self.has_background:
            self.contrail_coords.clear()
            bg = deque(maxlen=self.num_calib_frames)
            # Create blank images to send to display
            blank = np.zeros(shape=VID_DIM_RGB, dtype=np.uint8)
            fnum = -1
            # Start acquiring background
            acq_start = time.perf_counter()
            while not len(bg) >= self.num_calib_frames:
                if len(bg) > fnum:
                    fnum_frame = blank.copy()
                    cv2.putText(fnum_frame, 'Acquiring Background ({}/{})'.format(len(bg) + 1, self.num_calib_frames),
                                (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
                    self.frame_buffer.put_nowait(fnum_frame)
                    fnum += 1
                if self.input_array.can_recv_img():
                    bg.append(self.image_iterator())
                    self.input_array.set_can_send_img()
                else:
                    time.sleep(3.0 / 1000.0)
            print('Background Acquired in {} '
                  'Seconds for {} Frames at '
                  '{} FPS.'.format(round(time.perf_counter()-acq_start, 2), self.num_calib_frames, CAMERA_FRAMERATE))
            bg = np.array(bg)
            self.background = self.accum_fn(bg, axis=0)
            self.bg_original = self.background.copy()
            self.has_background = True
            if len(self.bounding_coords) == 2:
                self.crop_to_bounds(self.background)
            # We send the new background to be saved at output
            self.msg_proc_handler(cmd=CMD_NEW_BACKGROUND, val=(self.background, self.bg_original))
            # Reset Coords output
            self.reset_coords_output = True

    def get_kernel(self):
        """Get kernel from opening radius"""
        self.kernel = np.zeros((self.opening_radius, self.opening_radius))
        c = self.opening_radius / 2.
        for i in range(self.opening_radius):
            for j in range(self.opening_radius):
                if (i - c) ** 2 + (j - c) ** 2 <= self.opening_radius ** 2:
                    self.kernel[i, j] = 1

    def track_mouse(self, frame):
        """Tracks motion against background generated in get_bg()"""
        # Return coords, frame
        disp_frame = frame.copy().astype('uint8')
        cx, cy = None, None
        # Do we have boundaries? If so, crop frame so that areas outside boundaries are not tracked
        if len(self.bounding_coords) == 2:
            self.crop_to_bounds(frame)
            if self.show_only_tracked_space:
                self.crop_to_bounds(disp_frame)
        # Find differences and contours
        diff = frame - self.background
        th = (diff < self.thresh).astype('uint8') * 255
        seg = cv2.morphologyEx(th, cv2.MORPH_OPEN, self.kernel)
        seg = seg.astype('uint8')
        _, contours, hierarchy = cv2.findContours(seg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # Generate image with basic cv2 drawings
        disp_frame = np.dstack((disp_frame, disp_frame, disp_frame))  # RGB Stack
        if self.targ_perim.draw:
            cv2.circle(disp_frame, (self.targ_perim.x, self.targ_perim.y), self.targ_perim.radius,
                       (0, 255, 0), thickness=2)
        if not contours:
            cv2.putText(disp_frame, 'x, y: (NA, NA)', org=(10, 460), color=(255, 0, 0),
                        fontFace=cv2.FONT_HERSHEY_COMPLEX, fontScale=0.35)
            if len(self.bounding_coords) == 2:
                cv2.rectangle(disp_frame, self.bounding_coords[0], self.bounding_coords[1], (255, 255, 255))
            return disp_frame, (cx, cy)
        # Generate Contours
        contour_area = np.array([cv2.contourArea(c) for c in contours])
        contour_area = np.abs(contour_area - self.tracking_size)
        select_contour = np.argmin(contour_area)
        moments = cv2.moments(contours[select_contour])
        # Generate image with contours drawn
        try:
            cx = int(moments['m10'] / moments['m00'])
            cy = int(moments['m01'] / moments['m00'])
        except ZeroDivisionError:
            print('ZeroDivisionError, passing this frame.')
            cv2.putText(disp_frame, 'x, y: (NA, NA)', org=(10, 460), color=(255, 0, 0),
                        fontFace=cv2.FONT_HERSHEY_COMPLEX, fontScale=0.35)
        else:
            cv2.circle(disp_frame, (cx, cy), 3, (0, 0, 255), thickness=-1)
            loc = 'x, y: ({}, {})'.format(cx, cy)
            cv2.putText(disp_frame, loc, org=(10, 460), color=(255, 0, 0), fontFace=cv2.FONT_HERSHEY_COMPLEX,
                        fontScale=0.35)
        cv2.drawContours(disp_frame, contours, select_contour, (0, 255, 0), 1)
        if len(self.bounding_coords) == 2:
                cv2.rectangle(disp_frame, self.bounding_coords[0], self.bounding_coords[1], (255, 255, 255))
        return disp_frame, (cx, cy)

    def process_coords(self, frame, coord):
        """Takes supplied coordinates and generate movement direction + trail"""
        self.contrail_coords.appendleft(coord)
        size = len(self.contrail_coords)
        # Generate contrails
        for i in np.arange(1, size):
            thickness = int(np.sqrt(32.0 / (i + 1)) * 2.5)
            cv2.line(frame, self.contrail_coords[i - 1], self.contrail_coords[i], (255, 0, 0), thickness)
        # Generate Movement Direction
        if size >= 10:
            curr = self.contrail_coords[0]
            last = self.contrail_coords[-10]
            dx = curr[0] - last[0]
            dy = curr[1] - last[1]
            dir_x, dir_y = '', ''
            if np.abs(dx) > 20:
                dir_x = 'Right' if np.sign(dx) == 1 else 'Left'
            if np.abs(dy) > 20:
                dir_y = 'Down' if np.sign(dy) == 1 else 'Up'
            if dir_x and dir_y:
                direction = '{}-{}'.format(dir_x, dir_y)
            else:
                direction = dir_x if dir_x else dir_y
            cv2.putText(frame, direction, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (255, 0, 0), 2)
            cv2.putText(frame, 'dx, dy: ({}, {})'.format(dx, dy), (10, 470), cv2.FONT_HERSHEY_SIMPLEX,
                        0.35, (255, 0, 0), 1)
        # Return processed frame
        return frame

    # Misc Image Display Options
    def crop_to_bounds(self, frame):
        """Crops a supplied frame to bounding coordinates"""
        x1, y1 = self.bounding_coords[0]
        x2, y2 = self.bounding_coords[1]
        frame[:y1] = 0
        frame[y2:] = 0
        frame[:, :x1] = 0
        frame[:, x2:] = 0

    def toggle_show_cropped_img(self):
        """Toggle showing tracked space only or entire image"""
        self.show_only_tracked_space = not self.show_only_tracked_space

    def recv_new_bounds(self, bounding_coords):
        """Update bounding coordinates to new bounds"""
        if bounding_coords:
            self.bounding_coords = bounding_coords
            self.crop_to_bounds(self.background)
        else:
            self.bounding_coords = []
            self.background = self.bg_original.copy()
        # We send the new background to be saved at output
        self.msg_proc_handler(cmd=CMD_NEW_BACKGROUND, val=(self.background, self.bg_original))

    # Error Display
    def setup_error_img(self):
        """Create an error img that we show to GUI when error"""
        self.error_img = np.zeros(VID_DIM_RGB)
        cv2.putText(self.error_img, 'CAMERA ERROR. RECONNECT USB',
                    (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)

    def display_error_img(self):
        """If camera process encountered an error, we will display an error image to notify user"""
        self.frame_buffer.put_nowait(self.error_img)
