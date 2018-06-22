# coding=utf-8

"""Processes CV2 Coordinates into paths and heatmap"""

import cv2
import time
import serial
import numpy as np
from collections import deque
import threading as thr
import multiprocessing as mp
from pyfirmata import Arduino
from Misc.GlobalVars import *
from Misc.CustomFunctions import format_secs
from Misc.CustomClasses import StoppableProcess, ReadMessage, StopWatch, NewMessage
from GUI.DataDisplays.SendRecvProtocols import SyncableMPArray
from Concurrency.CV2Proc import CV2TargetAreaPerimeter
import queue as Queue


# Stimulate mouse for STIM_ON seconds every STIM_TOTAL seconds
STIM_ON = 0.4
STIM_TOTAL = 1.0
# Thread names
POLLING = 'polling'
SEND_SIGNAL = 'send_signal'
# Arduino Pin
ARDPIN = 6


class ArduinoDevice(object):
    """Connects to external arduino hardware"""
    def __init__(self):
        self.main_pin = 'd:{}:o'.format(ARDPIN)  # digital, pin 6, output
        self.test_pin = 'd:13:o'  # ask arduino for connection status. Added benefit of seeing LED 13 as visual aid
        self.ping_state = 0
        self.ping_interval = 1
        self.ping_timer = StopWatch()
        self.ping_timer.start()
        self.manual_mode = False
        self.connected = False

    def connect(self):
        """Attempts to connect to the device"""
        self.connected = False
        for port in range(1, 256+1):
            port = 'COM{}'.format(port)
            try:
                temp1 = serial.Serial(port)
                temp1.flush()
                temp1.close()
                self.board = Arduino(port)
            except serial.serialutil.SerialException:
                try:
                    self.board.exit()
                except AttributeError:
                    try:
                        temp2 = serial.Serial(port)
                    except serial.serialutil.SerialException:
                        pass
                    else:
                        temp2.flush()
                        temp2.close()
            else:
                self.main_output = self.board.get_pin(self.main_pin)
                self.test_output = self.board.get_pin(self.test_pin)
                print('Arduino Port Found at: {}'.format(port))
                self.connected = True
                break

    def toggle_manual(self):
        """Turns manual mode on or off"""
        self.manual_mode = not self.manual_mode

    def __send_signal__(self):
        """Sends a pulse"""
        self.write(1)
        time.sleep(STIM_ON)
        self.write(0)

    def send_signal(self):
        """Sends a pulse using a worker thread"""
        thread = thr.Thread(target=self.__send_signal__, daemon=True, name=SEND_SIGNAL)
        thread.start()

    def write(self, num):
        """Writes to arduino while handling any serial errors"""
        try:
            self.main_output.write(num)
        except (serial.serialutil.SerialTimeoutException, serial.serialutil.SerialException, AttributeError):
            self.connected = False

    def exit(self):
        """Close device cleanly"""
        try:
            self.board.exit()
        except (serial.serialutil.SerialException, serial.serialutil.SerialTimeoutException, AttributeError):
            pass

    def ping(self):
        """test if arduino is still connected"""
        if self.ping_timer.elapsed() > self.ping_interval:
            try:
                self.ping_state ^= 1
                self.test_output.write(self.ping_state)
            except (serial.serialutil.SerialTimeoutException, serial.serialutil.SerialException, AttributeError):
                self.connected = False
            finally:
                self.ping_timer.reset()
                self.ping_timer.start()


class ProgressBar(object):
    """Numpy Array based progress bar"""
    def __init__(self, initial_duration):
        self.mp_array = SyncableMPArray((PROGBAR_HEIGHT, *VID_DIM_RGB[1:]))
        # -- Constants -- #
        # Total segments in progress bar (= horizontal length)
        self.num_steps = VID_DIM_RGB[1]
        # Text Constants
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.text_vloc = 15
        self.text_size = 0.45
        self.text_thickness = 1
        self.text_dims = cv2.getTextSize('00:00.000', self.font, self.text_size, self.text_thickness)[0]
        spacing = self.text_dims[0] // 2
        self.txt_left_lmt = spacing
        self.txt_right_lmt = self.num_steps - spacing
        # -- Main thread vars -- #
        # Operation Params
        self.curr_loc = -1
        self.text_hloc = 0
        self.start_time = None
        self.output_array = None
        self.image = None
        self.displaying_error_image = False
        self.targ_perim = CV2TargetAreaPerimeter()
        # Progress bar segments for each element
        self.pbar_slice = None
        self.mouse_in_targ_slice = None
        self.mouse_stim_slice = None
        # Mouse Status
        self.mouse_in_target = False  # is mouse inside target region?
        self.mouse_recv_stim = False  # does mouse receive stimulation?
        self.mouse_stim_timer = None  # timer to make sure mouse receives STIM_ON secs stim, max every STIM_TOTAL secs
        self.in_targ_stopwatch = StopWatch()  # total time spent in target region
        self.get_stim_stopwatch = StopWatch()  # total time spent receiving stimulation
        self.mouse_n_entries = 0  # num entries into target region
        self.mouse_n_stims = 0  # num stimulations received
        # -- Modifier vars (read-only for main thread) -- #
        # Operation Params
        self._running = False
        self._duration = initial_duration

    # Initializing functions. Call once once new process starts
    def init_unpickleable_objs(self):
        """These objects must be created in the process they will run in"""
        self.output_array = self.mp_array.generate_np_array()
        self.image = self.output_array.copy()
        # Progress bar slices
        self.pbar_slice = self.image[20:60, :, :1]
        self.mouse_in_targ_slice = self.image[20:40, :, 1:2]
        self.mouse_stim_slice = self.image[40:60, :, 2:3]
        # Text slices
        w, h = self.text_dims
        self.main_timer_slice = self.image[:self.text_vloc+5, :, :]
        self.targ_timer_slice = self.image[92-h:92+5, 95:95+w, :]
        self.stim_timer_slice = self.image[92-h:92+5, 411:411+w, :]
        self.targ_count_slice = self.image[92-h:92+5, 256:256+int(w*3/4), :]
        self.stim_count_slice = self.image[92-h:92+5, 563:563+int(w*3/4), :]
        # Arduino object
        cv2.putText(self.output_array, 'CONNECTING TO ARDUINO...', (30, 63),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 255), 1)
        self.output_array.set_can_recv_img()
        self.arduino = ArduinoDevice()
        self.arduino.connect()  # this step takes a few seconds
        self.output_array.fill(0)
        # Set Progress bar to initial conditions
        self.reset_bar()

    # Modifier Functions. Can call from other threads
    # *** Non-underscored variables are READ ONLY
    def set_duration(self, duration_in_secs):
        self._duration = float(duration_in_secs)

    def set_start(self):
        self._running = True
        self.reset_bar()

    def set_stop(self):
        self._running = False

    # Main Update Function. Run in Main Thread. Do NOT call from any other thread
    # *** Underscored variables are READ ONLY
    def set_timer_text(self, reset):
        """Places cv2 text on output array"""
        if reset:
            main_timer = '00:00.000'
            mouse_in_region_timer = '00:00.000'
            mouse_recv_stim_timer = '00:00.000'
            num_entries = '0)'
            num_stims = '0)'
        else:
            main_timer = format_secs(time.perf_counter() - self.start_time, 'with_ms')
            mouse_in_region_timer = format_secs(self.in_targ_stopwatch.elapsed(), 'with_ms')
            mouse_recv_stim_timer = format_secs(self.get_stim_stopwatch.elapsed(), 'with_ms')
            num_entries = '{})'.format(self.mouse_n_entries)
            num_stims = '{})'.format(self.mouse_n_stims)
        self.main_timer_slice.fill(0)
        self.targ_timer_slice.fill(0)
        self.stim_timer_slice.fill(0)
        self.targ_count_slice.fill(0)
        self.stim_count_slice.fill(0)
        cv2.putText(self.main_timer_slice, main_timer, (self.text_hloc, self.text_vloc),
                    fontFace=self.font, fontScale=self.text_size, color=(255, 255, 255))
        cv2.putText(self.targ_timer_slice, mouse_in_region_timer, (0, self.text_dims[1]),
                    fontFace=self.font, fontScale=self.text_size, color=(255, 255, 255))
        cv2.putText(self.stim_timer_slice, mouse_recv_stim_timer, (0, self.text_dims[1]),
                    fontFace=self.font, fontScale=self.text_size, color=(255, 255, 255))
        cv2.putText(self.targ_count_slice, num_entries, (0, self.text_dims[1]),
                    fontFace=self.font, fontScale=self.text_size, color=(255, 255, 255))
        cv2.putText(self.stim_count_slice, num_stims, (0, self.text_dims[1]),
                    fontFace=self.font, fontScale=self.text_size, color=(255, 255, 255))
        # Image is now fully prepared, send
        self.output_array.send_img(self.image)

    def check_mouse_inside_target(self, coord):
        """Checks if mouse is inside target region"""
        x, y = coord
        self.mouse_in_target = False
        if not self.targ_perim.draw or coord == (None, None):
            return
        x1, x2, y1, y2 = self.targ_perim.x1, self.targ_perim.x2, self.targ_perim.y1, self.targ_perim.y2
        if x1 <= x <= x2 and y1 <= y <= y2:
            self.mouse_in_target = True

    def send_stim_to_mouse(self):
        """Stim mouse if inside region"""
        if self.mouse_stim_timer:
            elapsed = time.perf_counter() - self.mouse_stim_timer
            if STIM_ON > elapsed:
                return
            elif STIM_ON <= elapsed < STIM_TOTAL:
                self.mouse_recv_stim = False
                return
            elif STIM_TOTAL <= elapsed:
                if self.mouse_in_target:
                    self.mouse_recv_stim = True
                    self.mouse_stim_timer = time.perf_counter()
                    return
                elif not self.mouse_in_target:
                    self.mouse_recv_stim = False
                    self.mouse_stim_timer = None
                    return
        else:
            if self.mouse_in_target:
                self.mouse_recv_stim = True
                self.mouse_stim_timer = time.perf_counter()

    def reset_bar(self):
        """Resets to initial conditions"""
        # Reset Locations
        self.curr_loc = -1
        self.text_hloc = 0
        # Reset Mouse Location timers and counters
        self.in_targ_stopwatch.reset()
        self.get_stim_stopwatch.reset()
        self.mouse_n_entries = 0
        self.mouse_n_stims = 0
        self.mouse_stim_timer = None
        # Reset Progress Bar Image
        self.reset_progbar_img()
        # Send Image
        self.output_array.set_can_recv_img()

    def reset_progbar_img(self):
        """Reset progressbar to initial image"""
        self.image.fill(0)
        # Add new progress bar at origin
        self.pbar_slice[:, :1, :] = 255
        # Add time indicators
        self.image[61:62, :, :] = 255
        num_chunks = int(self._duration / 30)
        num_chunks = min([12, num_chunks])
        num_chunks = max([2, num_chunks])
        seg_size = int(self.image.shape[1] / num_chunks)
        time_chunk = (self._duration / num_chunks)
        for i in np.arange(1, num_chunks):
            loc = seg_size * i
            tloc = format_secs(time_chunk * i)
            self.image[62:65, loc - 1:loc, :] = 255
            cv2.putText(self.image, tloc, (loc - 15, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255))
        # Add legends
        self.image[79:96, 319:320, :] = 255
        self.image[80:95, 3:18, 1] = 255
        cv2.putText(self.image, 'In Region:', (19, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255))
        cv2.putText(self.image, '(# Entries:', (175, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255))
        self.image[80:95, 323:338, 2] = 255
        cv2.putText(self.image, 'Get Stim:', (340, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255))
        cv2.putText(self.image, '(# Stims:', (491, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255))
        # add initializing timer text
        self.set_timer_text(reset=True)

    def can_update(self):
        """Checks we are allowed to proceed"""
        finished = self.curr_loc >= self.num_steps
        if finished or not self._running:
            return False
        return True

    def update(self):
        """Draws next frame of progress bar"""
        # Get elapsed time, get expected location, check mouse location/stim status
        elapsed = time.perf_counter() - self.start_time
        loc = int((elapsed / self._duration) * self.num_steps)
        # Check if mouse in target region; also calculate total time inside
        if self.mouse_in_target:
            self.mouse_in_targ_slice[:, loc - 1:loc, :] = 255
            if not self.in_targ_stopwatch.started:
                self.mouse_n_entries += 1
                self.in_targ_stopwatch.start()
        else:
            if self.in_targ_stopwatch.started:
                self.in_targ_stopwatch.stop()
        # Check if mouse receive stimulation; calculate total time receive
        if self.mouse_recv_stim:
            self.mouse_stim_slice[:, loc - 1:loc, :] = 255
            if not self.get_stim_stopwatch.started:
                self.mouse_n_stims += 1
                self.get_stim_stopwatch.start()
                if not self.arduino.manual_mode:
                    self.arduino.send_signal()
        else:
            if self.get_stim_stopwatch.started:
                self.get_stim_stopwatch.stop()
        # If enough time elapsed, update current location to expected location
        if loc != self.curr_loc:
            self.pbar_slice[:, self.curr_loc - 1:self.curr_loc, :] = 0
            self.pbar_slice[:, loc - 1:loc + 1, :] = 255
            if self.txt_left_lmt <= loc <= self.txt_right_lmt:
                self.text_hloc = loc - self.txt_left_lmt
            self.curr_loc = loc
        # Test for arduino connection; send new progbar frame; attempt to reconnect lost devices
        self.ping_arduino(updating=True)

    def ping_arduino(self, updating):
        """Pings arduino, displays errors, attempt to reconnect"""
        self.arduino.ping()
        if self.output_array.can_send_img():
            if not self.arduino.connected:
                self.display_error_img()
            elif updating:
                self.set_timer_text(reset=False)
            elif not updating and self.displaying_error_image:
                self.displaying_error_image = False
                self.output_array[:] = self.image
            self.output_array.set_can_recv_img()
        if not self.arduino.connected:
            self.arduino.connect()

    def display_error_img(self):
        if not self.displaying_error_image:
            self.displaying_error_image = True
            self.output_array.fill(0)
            cv2.putText(self.output_array, 'ARDUINO ERROR. RECONNECT DEVICE', (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        1, (255, 255, 255), 2)


class Heatmap(object):
    """Generates heatmap from coordinates"""
    def __init__(self):
        self.mp_array = SyncableMPArray(MAP_DIMS)
        # Constants
        self.num_rows = 12
        self.num_cols = 16
        self.row_scale = int(MAP_DIMS[0] / self.num_rows)
        self.col_scale = int(MAP_DIMS[1] / self.num_cols)
        # Main thread vars
        self.bins = np.zeros((self.num_rows, self.num_cols), dtype='uint32')
        self.empty = np.zeros((self.num_rows, self.num_cols), dtype='uint8')

    # Initializing functions. Call once once new process starts
    def init_unpickleable_objs(self):
        """These objects must be created in the process they will run in"""
        self.output_array = self.mp_array.generate_np_array()
        self.output_array.set_can_recv_img()

    # Modifier Functions. Can call from other threads
    # *** Non-underscored variables are READ ONLY
    def reset(self):
        self.bins.fill(0)
        self.output_array.fill(0)

    # Main Update Function. Run in Main Thread. Do NOT call from any other thread
    # *** Underscored variables are READ ONLY
    def update(self, coord):
        """Update heatmap with supplied coord"""
        col, row = coord
        # Find bins this coord belongs to, and add to bin
        if row is not None and col is not None:
            rowbin = int(row / (self.row_scale * MAP_DOWNSCALE))
            colbin = int(col / (self.col_scale * MAP_DOWNSCALE))
            self.bins[rowbin, colbin] += 1
            # We use a black-yellow-red gradient.
            red = self.bins.copy()
            green = self.bins.copy()
            # Create Gradient
            red = (red / red.max()) * 2 * 255
            red = np.clip(red, 0, 255)
            green = (green / green.max()) * 2 * 255
            green[green > 255] = 255 - (green[green > 255] - 255)
            # Retype into 8 bits
            red = red.astype('uint8')
            green = green.astype('uint8')
            # Create Image; blue is empty.
            bins = np.dstack((red, green, self.empty))
            heatmap = np.kron(bins, np.ones((self.row_scale, self.col_scale, 1), dtype='uint8'))
            self.output_array.send_img(heatmap)
        # Update Gradient
        return self.bins.min(), self.bins.max()

    # Generate Output from List of Coords
    def get_heatmap(self, coord_list):
        """Provided a full list of coords, generate a full size map"""
        bins = np.zeros((self.num_rows, self.num_cols), dtype='uint32')
        empty = np.zeros((self.num_rows, self.num_cols), dtype='uint8')
        row_scale = int(VID_DIM_RGB[0] / self.num_rows)
        col_scale = int(VID_DIM_RGB[1] / self.num_cols)
        for col, row in coord_list:
            if row is not None and col is not None:
                rowbin = int(row / row_scale)
                colbin = int(col / col_scale)
                bins[rowbin, colbin] += 1
        red = bins.copy()
        green = bins.copy()
        # Create Gradient (black yellow red)
        if bins.max() > 0:
            red = (red / red.max()) * 2 * 255
            red = np.clip(red, 0, 255)
            green = (green / green.max()) * 2 * 255
            green[green > 255] = 255 - (green[green > 255] - 255)
        # Retype into 8 bits
        red = red.astype('uint8')
        green = green.astype('uint8')
        # Create BGR Image (cv2 imwrite takes BGR)
        stacked = np.dstack((empty, green, red))
        heatmap = np.kron(stacked, np.ones((row_scale, col_scale, 1), dtype='uint8'))
        # Add bin text
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                num = int(bins[row, col])
                if num < bins.max() / 3:
                    color = (255, 255, 255)
                else:
                    color = (0, 0, 0)
                cv2.putText(heatmap, str(num), (col*col_scale+5, row*row_scale+25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
        return bins.min(), bins.max(), heatmap


class Pathing(object):
    """Generates pathing map from coordinates"""
    def __init__(self):
        self.mp_array = SyncableMPArray(MAP_DIMS)
        # Main thread vars
        self.last_coord = None

    # Initializing functions. Call once once new process starts
    def init_unpickleable_objs(self):
        """These objects must be created in the process they will run in"""
        self.output_array = self.mp_array.generate_np_array()
        self.output_array.set_can_recv_img()

    # Modifier Functions. Can call from other threads
    # *** Non-underscored variables are READ ONLY
    def reset(self):
        self.last_coord = None
        self.output_array.fill(0)

    # Main Update Function. Run in Main Thread. Do NOT call from any other thread
    # *** Underscored variables are READ ONLY
    def update(self, coord):
        """Draw new pathing segment on pathing array"""
        col, row = coord
        if col is not None and row is not None:
            # Scale coords
            if MAP_DOWNSCALE > 1:
                coord = round(col / MAP_DOWNSCALE), round(row / MAP_DOWNSCALE)
            # Draw new path segment
            if self.last_coord:
                cv2.line(self.output_array, coord, self.last_coord, (0, 255, 0), 1)
            self.last_coord = coord

    # Generate Output from List of Coords
    @staticmethod
    def get_pathmap(coord_list):
        """Provided a full list of coords, generate a full size map"""
        last_path_coord = None
        pathmap = np.zeros(VID_DIM_RGB, dtype='uint8')
        for coord in coord_list:
            if coord != (None, None):
                if last_path_coord:
                    cv2.line(pathmap, coord, last_path_coord, (0, 255, 0), 1)
                last_path_coord = coord
        return pathmap


class Gradient(object):
    """Generates a gradient with variable labels from coordinates"""
    def __init__(self):
        self.mp_array = SyncableMPArray((GRADIENT_HEIGHT, *MAP_DIMS[1:]))
        # Constants
        self.label_y = 15
        self.label_xmin = (3, self.label_y)
        self.label_xmax_shift = MAP_DIMS[1] - 10
        # Main thread vars
        self.last_min, self.last_max = -1, -1

    # Initializing functions. Call once once new process starts
    def init_unpickleable_objs(self):
        """These objects must be created in the process they will run in"""
        self.output_array = self.mp_array.generate_np_array()
        self.init_gradient()
        self.output_array.set_can_recv_img()

    def init_gradient(self):
        """Create gradient indicator"""
        num_grads = 32
        raw = np.zeros((1, num_grads))
        for col in range(num_grads):
            raw[:, col] = col
        empty = np.zeros((1, num_grads), dtype='uint8')
        # Create red and green channels.
        red = raw.copy()
        green = raw.copy()
        # Generate gradient. we use a black-yellow-red gradient.
        red = (red / red.max()) * 2 * 255
        red = np.clip(red, 0, 255)
        green = (green / green.max()) * 2 * 255
        green[green > 255] = 255 - (green[green > 255] - 255)
        # Retype into 8 bits
        red = red.astype('uint8')
        green = green.astype('uint8')
        # Create image
        image = np.dstack((red, green, empty))
        col_scale = int(MAP_DIMS[1] / num_grads)
        self.gradient = np.kron(image, np.ones((GRADIENT_HEIGHT, col_scale, 1), dtype='uint8'))
        self.text_slice = self.gradient[(GRADIENT_HEIGHT//2-10):(GRADIENT_HEIGHT//2+10), :, :]
        # Send gradient image
        self.output_array.send_img(self.gradient)

    # Modifier Functions. Can call from other threads
    # *** Non-underscored variables are READ ONLY
    def reset(self):
        self.last_min, self.last_max = -1, -1
        self.update(0, 0)

    # Main Update Function. Run in Main Thread. Do NOT call from any other thread
    # *** Underscored variables are READ ONLY
    def update(self, minimum, maximum):
        """Update scale on gradient"""
        if minimum == self.last_min and maximum == self.last_max:
            return
        # Reset text
        self.text_slice[:] = self.gradient[:20, :, :]
        # Find x location of maximum label
        label_xmax = self.label_xmax_shift - (len(str(maximum)) * 5)
        label_xmax = (label_xmax, self.label_y)
        # Label gradient
        cv2.putText(self.text_slice, str(minimum), self.label_xmin,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        cv2.putText(self.text_slice, str(maximum), label_xmax,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
        # Send to shared array
        self.output_array.send_img(self.gradient)
        # Remember min and max
        self.last_min, self.last_max = minimum, maximum

    # Append a gradient to a heatmap, given min and max
    @staticmethod
    def append_gradient(minimum, maximum, heatmap):
        """Append gradient"""
        num_grads = 64
        raw = np.zeros((1, num_grads))
        for col in range(num_grads):
            raw[:, col] = col
        empty = np.zeros((1, num_grads), dtype='uint8')
        # Create red and green channels.
        red = raw.copy()
        green = raw.copy()
        # Generate gradient. we use a black-yellow-red gradient.
        red = (red / red.max()) * 2 * 255
        red = np.clip(red, 0, 255)
        green = (green / green.max()) * 2 * 255
        green[green > 255] = 255 - (green[green > 255] - 255)
        # Retype into 8 bits
        red = red.astype('uint8')
        green = green.astype('uint8')
        # Create gradient (cv2 imwrite takes BGR)
        image = np.dstack((empty, green, red))
        col_scale = int(VID_DIM_RGB[1] / num_grads)
        gradient = np.kron(image, np.ones((GRADIENT_HEIGHT//2, col_scale, 1), dtype='uint8'))
        # Add min max labels
        y = 30
        xmax = VID_DIM_RGB[1] - 8 - len(str(maximum) * 10), y
        xmin = 3, y
        # Label gradient
        cv2.putText(gradient, str(minimum), xmin,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(gradient, str(maximum), xmax,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        # Append to heatmap
        shape = heatmap.shape[0]+GRADIENT_HEIGHT//2, heatmap.shape[1], 3
        output = np.zeros(shape, dtype='uint8')
        output[:heatmap.shape[0], :, :] = heatmap
        output[heatmap.shape[0]:, :, :] = gradient
        return output


class CoordinateProcessor(StoppableProcess):
    """Processes CV2 Coordinates"""
    def __init__(self, coords_queue, initial_duration):
        super(CoordinateProcessor, self).__init__()
        self.connected = True
        self.initialize_experiment = False
        self.name = PROC_COORDS
        self.input_msgs = mp.Queue()
        self.output_msgs = PROC_HANDLER_QUEUE
        self.parent_pipe, self.pipe = mp.Pipe()
        self.exp_start_event = EXP_START_EVENT
        # Output deque for coords, coord times, and mouse in region/get stim status
        self.all_coords = deque()
        self.coords_saved = True
        self._reset_coords = False
        self._save_name = None
        # Input source
        self.input_queue = coords_queue
        # Mapping Objects
        self.heatmap = Heatmap()
        self.pathing = Pathing()
        self.gradient = Gradient()
        self.progbar = ProgressBar(initial_duration)

    # Initializing functions. Call once once new process starts
    def init_unpickleable_objs(self):
        """Initializes objs that must be created in the process it runs in"""
        for obj in (self.heatmap, self.pathing, self.gradient, self.progbar):
            obj.init_unpickleable_objs()
        self.setup_msg_parser()

    def setup_msg_parser(self):
        """Dictionary of {Msg:Actions}"""
        self._msg_parser = {
            CMD_START: lambda trial_params: self.run_experiment(run=True, trial_params=trial_params),
            CMD_STOP: lambda val: self.run_experiment(run=False, trial_params=None),
            CMD_EXIT: lambda val: self.stop(),
            CMD_SET_TIME: lambda ttl_time: self.set_ttl_time(ttl_time),
            CMD_CLR_MAPS: lambda val: self.reset_maps(),
            CMD_TARG_DRAW: lambda params: self.progbar.targ_perim.toggle_draw(params),
            CMD_TARG_RADIUS: lambda radius: self.progbar.targ_perim.update_radius(radius),
            CMD_TOGGLE_MANUAL_TRIGGER: lambda val: self.progbar.arduino.toggle_manual(),
            CMD_SEND_STIMULUS: lambda val: self.progbar.arduino.send_signal()
        }

    # Message read/write/process functions. CALL IN CHILD THREADS
    # *** Non-underscored variables are READ ONLY
    def run_experiment(self, run, trial_params):
        """Clears maps, starts experiment"""
        if run:
            self.set_save_name(trial_params[0])
            self.initialize_experiment = True
        elif not run:
            self.progbar.set_stop()

    def set_save_name(self, save_name):
        self._save_name = save_name

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

    # Main Update Function. Run in Main Thread. Do NOT call from any other thread
    # *** Underscored variables are READ ONLY
    def reset_maps(self):
        """Resets heatmap, pathing map, gradient"""
        for obj in (self.heatmap, self.pathing, self.gradient):
            obj.reset()

    def setup_experiment(self):
        """Setup maps/progbar/data containers for next experiment trial"""
        # Reset Coordinate deque
        self.all_coords.clear()
        self.coords_saved = False
        # Reset pathing/heatmap/gradient
        self.reset_maps()
        # Reset Progressbar
        self.progbar.set_start()
        # Notify we are ready to begin and wait for start signal
        self.pipe.send(MSG_RECEIVED)
        self.exp_start_event.wait()
        self.progbar.start_time = time.perf_counter()

    def run(self):
        """Call using start(); spawns new process"""
        self.init_unpickleable_objs()
        # Threading
        thr_msg_polling = thr.Thread(target=self.msg_polling, name=POLLING, daemon=True)
        thr_msg_polling.start()
        # Main Process Loop
        while self.connected:
            if self.initialize_experiment:
                self.initialize_experiment = False
                self.setup_experiment()
            self.process_coords()
            if self.stopped():
                self.connected = False
                self.progbar.arduino.exit()
                while True:
                    time.sleep(5.0 / 1000.0)
                    threads = [thread.name for thread in thr.enumerate()]
                    if POLLING not in threads and SEND_SIGNAL not in threads:
                        break
        print('Exiting Coordinate Processor...')

    def process_coords(self):
        """Processes coordinates into heatmap and pathing map"""
        # Get coords, update all maps, send if able to
        try:
            coord = self.input_queue.get_nowait()
        except Queue.Empty:
            coord = None
            time.sleep(1.0 / 1000.0)
        else:
            # Check if mouse is inside target region
            self.progbar.check_mouse_inside_target(coord)
            # Update maps
            self.pathing.update(coord)
            min_max = self.heatmap.update(coord)
            self.gradient.update(*min_max)
            # Send new updates to gui if able. Send together so all 3 maps remain in sync
            send = (obj.output_array.can_send_img() for obj in (self.pathing, self.heatmap, self.gradient))
            if all(send):
                self.heatmap.output_array.set_can_recv_img()
                self.pathing.output_array.set_can_recv_img()
                self.gradient.output_array.set_can_recv_img()
        # We update progress bar regardless if there were new coordinates available
        # Update Progress Bar; if mouse inside target region, we determine if should stimulate
        if not self.progbar.can_update():
            self.progbar.ping_arduino(updating=False)
            if not self.coords_saved:
                self.coords_saved = True
                self.save_coords()
        else:
            # If progress bar is allowed to run/update, we assume exp is running so we send stim to mouse
            self.progbar.send_stim_to_mouse()
            self.progbar.update()
            if coord:
                self.append_coords(coord)

    def set_ttl_time(self, ttl_time):
        """Reformats progress bar with new duration"""
        self.progbar.set_duration(ttl_time)
        self.progbar.reset_bar()

    # Save coords and output to file at end of trial
    def append_coords(self, coord):
        """Add coords to deque, along with timing/mouse statuses"""
        time_elapsed = round(time.perf_counter()-self.progbar.start_time, 3)
        targ_elapsed = round(self.progbar.in_targ_stopwatch.elapsed(), 3)
        stim_elapsed = round(self.progbar.get_stim_stopwatch.elapsed(), 3)
        in_targ = self.progbar.mouse_in_target
        get_stim = self.progbar.mouse_recv_stim
        num_entries = self.progbar.mouse_n_entries
        num_stims = self.progbar.mouse_n_stims
        append = (time_elapsed, *coord,
                  in_targ, num_entries, targ_elapsed,
                  get_stim, num_stims, stim_elapsed)
        self.all_coords.append(append)

    def save_coords(self):
        """saves coords to file"""
        # Inform proc handler we are starting to save
        msg = NewMessage(dev=self.name, cmd=MSG_VIDREC_SAVING)
        self.output_msgs.put_nowait(msg)
        # Save coords to .csv
        file = '{}_Coords.csv'.format(self._save_name)
        with open(file, 'w') as f:
            # target region information
            for element in ('Target Region X', 'Target Region Y', 'Target Region Radius',
                            'Normalized X', 'Normalized Y'):
                f.write('{},'.format(element))
            f.write('\n')
            for element in (self.progbar.targ_perim.cx, self.progbar.targ_perim.cy, self.progbar.targ_perim.radius,
                            self.progbar.targ_perim.norm_x, self.progbar.targ_perim.norm_y):
                f.write('{},'.format(element))
            f.write('\n')
            # coords data
            for element in ('Total Time Elapsed (s)', 'Mouse X', 'Mouse Y',
                            'Mouse In Target', 'Num Entries', 'Time in Target (s)', 'Total Time in Target (s)',
                            'Mouse Get Stim', 'Num Stimulations', 'Total Stim Time (s)'):
                f.write('{},'.format(element))
            f.write('\n')
            last_entry_time = 0
            last_stored_time = 0
            last_num_entries = 0
            for line in self.all_coords:
                for index, element in enumerate(line):
                    f.write('{},'.format(element))
                    if index == 4:
                        if element != last_num_entries:
                            last_num_entries = element
                            last_entry_time = last_stored_time
                        f.write('{},'.format(line[5]-last_entry_time))
                        last_stored_time = line[5]
                f.write('\n')
        # Generate full size heatmap and pathing map
        coords = [(line[1], line[2]) for line in self.all_coords]
        pathmap = self.pathing.get_pathmap(coord_list=coords)
        heatmap = self.heatmap.get_heatmap(coord_list=coords)
        heatmap = self.gradient.append_gradient(*heatmap)
        quality = int(cv2.IMWRITE_PNG_COMPRESSION), 0
        cv2.imwrite(self._save_name+'_Heatmap.png', heatmap, quality)
        cv2.imwrite(self._save_name+'_Mouse_Path.png', pathmap, quality)
        # Inform proc handler we finished saving
        msg = NewMessage(dev=self.name, cmd=MSG_VIDREC_FINISHED)
        self.output_msgs.put_nowait(msg)
        print('Finished Saving Coordinates to File...')
