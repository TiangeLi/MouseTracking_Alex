# coding=utf-8

"""Experiment Controls for User Settings"""

import os
from copy import deepcopy
import numpy as np
import PyQt4.QtGui as qg
import PyQt4.QtCore as qc
from GUI.MiscWidgets import *
from Misc.GlobalVars import *
from Misc.CustomFunctions import format_secs
from Misc.CustomClasses import NewMessage
from DirsSettings.Settings import TargetAreas


# Utilities
class GuiTargAreaInfoDisplay(qg.QWidget):
    """Displays target area data"""
    def __init__(self, data):
        super(GuiTargAreaInfoDisplay, self).__init__()
        self.x = 'NA'
        self.y = 'NA'
        # Make widgets from data
        self.row_label = qg.QLabel('')
        self.scaled_lbl = qg.QLabel('')
        self.normalized_lbl = qg.QLabel('')
        self.tested_chkbox = qg.QCheckBox()
        # Widget layout
        self.row_label.setAlignment(qAlignCenter)
        self.scaled_lbl.setAlignment(qAlignCenter)
        self.normalized_lbl.setAlignment(qAlignCenter)
        self.tested_chkbox.setEnabled(False)
        # set data inside widgets
        self.set_data(data)

    def set_data(self, data):
        """reload backend data"""
        self.selected = False
        self.data = data
        self.row_label.setText(str(data.area_id + 1))
        self.scaled_lbl.setText('({}, {})'.format(self.x, self.y))
        self.normalized_lbl.setText('({0:.2f}, {1:.2f})'.format(data.x, data.y))
        self.tested_chkbox.setChecked(data.tested)
        self.set_color()

    def add_to_grid(self, grid):
        """Adds our widgets to a supplied grid"""
        row = self.data.area_id + 1
        grid.addWidget(self.row_label, row, 0)
        grid.addWidget(self.scaled_lbl, row, 1)
        grid.addWidget(self.normalized_lbl, row, 2)
        grid.addWidget(self.tested_chkbox, row, 3, qAlignCenter)

    def set_color(self):
        """Sets this widget to selected or not"""
        if self.selected:
            self.row_label.setStyleSheet(qBgCyan)
            self.scaled_lbl.setStyleSheet(qBgCyan)
            self.normalized_lbl.setStyleSheet(qBgCyan)
        else:
            self.row_label.setStyleSheet('')
            self.scaled_lbl.setStyleSheet('')
            self.normalized_lbl.setStyleSheet('')

    def set_xy_labels(self, x, y):
        """Changes scaled x and y"""
        self.x = x
        self.y = y
        self.scaled_lbl.setText('({}, {})'.format(self.x, self.y))


# Main Widgets
class GuiMainControls(qg.QWidget):
    """Widget window that manages all other config widgets"""
    def __init__(self, dirs):
        super(GuiMainControls, self).__init__()
        self.dirs = dirs
        self.grid = qg.QGridLayout()
        self.setLayout(self.grid)
        self.render_widgets()
        self.connect_internal_signals()

    def render_widgets(self):
        """generate and add widgets to grid"""
        self.targ_area_config = GuiTargetAreaConfigs(self.dirs)
        self.curr_exp_config = GuiStartStopControls(self.dirs)
        self.grid.addWidget(self.targ_area_config)
        self.grid.addWidget(self.curr_exp_config)

    def connect_internal_signals(self):
        """Connects child widget signal and slots"""
        self.targ_area_config.newTargAreasSignal.\
            connect(lambda: self.curr_exp_config.targ_region_selected(selected=False))


class GuiTargetAreaConfigs(qg.QGroupBox):
    """Changes Target Area Radius and displays target area settings"""
    newTargAreasSignal = qc.pyqtSignal()
    getNewLocSignal = qc.pyqtSignal()
    fineAdjustSignal = qc.pyqtSignal(tuple)

    def __init__(self, dirs):
        super(GuiTargetAreaConfigs, self).__init__('Mouse Target Region')
        self.dirs = dirs
        self.output_msgs = PROC_HANDLER_QUEUE
        self.grid = qg.QGridLayout()
        self.setLayout(self.grid)
        self.init_radius_widget()
        self.init_loc_widget()
        self.init_loc_adjust_widget()
        self.setMaximumSize(self.sizeHint())

    # Setup widgets
    def init_radius_widget(self):
        """Setup radius config and add to grid"""
        rad_label = qg.QLabel('Radius:')
        self.rad_entry = GuiIntOnlyEntry(max_digits=3, minimum=1, maximum=320)
        self.confirm_btn = qg.QPushButton('Update Radius')
        # Set Widget Params
        self.rad_entry.setMaximumWidth(80)
        self.rad_entry.setText(str(self.dirs.settings.target_area_radius))
        self.confirm_btn.clicked.connect(self.update_radius)
        # Add to grid
        self.grid.addWidget(rad_label, 0, 0)
        self.grid.addWidget(self.rad_entry, 0, 1)
        self.grid.addWidget(self.confirm_btn, 0, 2)

    def init_loc_widget(self):
        """Get and configure target location"""
        frame = GuiSimpleFrame('Get Target Area Center')
        self.get_loc_btn = GuiFlipBtn('Get Location', 'Cancel', flipped_color=qBgRed)
        self.get_loc_btn.clicked.connect(self.get_location)
        frame.addWidget(self.get_loc_btn)
        self.grid.addWidget(frame, 1, 0, 1, 3)

    def init_loc_adjust_widget(self):
        """Fine adjustment of target location"""
        frame = GuiSimpleFrame('Fine Adjustment')
        xlabel = qg.QLabel('X')
        xlabel.setAlignment(qAlignCenter)
        ylabel = qg.QLabel('Y')
        ylabel.setAlignment(qAlignCenter)
        self.xentry = GuiIntOnlyEntry(max_digits=3, default_text=self.dirs.settings.last_targ_areas.areas[0].x,
                                      minimum=0, maximum=VID_DIM[1])
        self.yentry = GuiIntOnlyEntry(max_digits=3, default_text=self.dirs.settings.last_targ_areas.areas[0].y,
                                      minimum=0, maximum=VID_DIM[0])
        self.xentry.setMaximumWidth(30)
        self.yentry.setMaximumWidth(30)
        self.set_loc_btn = qg.QPushButton('Confirm')
        self.set_loc_btn.clicked.connect(self.fine_adjust_loc)
        frame.addWidget(xlabel)
        frame.addWidget(ylabel, 0, 1)
        frame.addWidget(self.xentry, 1, 0)
        frame.addWidget(self.yentry, 1, 1)
        frame.addWidget(self.set_loc_btn, 1, 2)
        self.grid.addWidget(frame, 2, 0, 1, 3)

    # Update radius
    def update_radius(self):
        """Updates target area radius"""
        if self.rad_entry.text().strip() == '':
            self.rad_entry.visual_warning()
            return
        radius = int(self.rad_entry.text())
        self.dirs.settings.target_area_radius = radius
        msg = NewMessage(cmd=CMD_TARG_RADIUS, val=radius)
        self.output_msgs.put_nowait(msg)

    # Get New Location
    def get_location(self):
        """Signals to get new target location"""
        self.get_loc_btn.toggle_state()
        self.getNewLocSignal.emit()
        self.confirm_btn.setEnabled(not self.confirm_btn.isEnabled())
        self.rad_entry.setEnabled(not self.rad_entry.isEnabled())
        self.xentry.setEnabled(not self.xentry.isEnabled())
        self.yentry.setEnabled(not self.yentry.isEnabled())
        self.set_loc_btn.setEnabled(not self.set_loc_btn.isEnabled())

    def got_location(self, loc):
        self.get_loc_btn.toggle_state()
        self.confirm_btn.setEnabled(not self.confirm_btn.isEnabled())
        self.rad_entry.setEnabled(not self.rad_entry.isEnabled())
        self.xentry.setEnabled(not self.xentry.isEnabled())
        self.yentry.setEnabled(not self.yentry.isEnabled())
        self.set_loc_btn.setEnabled(not self.set_loc_btn.isEnabled())
        self.xentry.setText(str(loc[0]))
        self.yentry.setText(str(loc[1]))

    # Fine adjustment
    def fine_adjust_loc(self):
        """Sends finely adjusted location data"""
        x = abs(int(self.xentry.text().strip()))
        y = abs(int(self.yentry.text().strip()))
        self.fineAdjustSignal.emit((x, y))


class GuiStartStopControls(qg.QGroupBox):
    """Entries and buttons to setup for recording/running experiment"""
    expStartedSignal = qc.pyqtSignal(bool, tuple)

    def __init__(self, dirs):
        super(GuiStartStopControls, self).__init__('Experiment Controls')
        self.dirs = dirs
        self.output_msgs = PROC_HANDLER_QUEUE
        self.grid = qg.QGridLayout()
        self.setLayout(self.grid)
        self.render_set_time()
        self.render_saving()
        self.render_naming_start()

    def render_naming_start(self):
        """Creates a widget that allows naming the next trial and start/stop functions"""
        name_label = qg.QLabel('Trial Name: ')
        self.name_entry = GuiEntryWithWarning()
        self.start_btn = GuiMultiStateBtn('Select a Target Region', default_color=qBgOrange,
                                          START=('START', qBgCyan), STOP=('STOP', qBgRed),
                                          SAVING_VIDEOS=('Saving Videos...', qBgOrange))
        # Set widgets to initial state
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.run_experiment)
        self.targ_region_selected(selected=True)
        # add to grid
        self.grid.addWidget(name_label, 0, 0)
        self.grid.addWidget(self.name_entry, 0, 1)
        self.grid.addWidget(self.start_btn, 1, 0, 1, 2)

    def render_set_time(self):
        """Creates a widget for setting total time"""
        frame = GuiSimpleFrame('Set Total Time')
        self.grid.addWidget(frame, 2, 0, 1, 2)
        mins_label = qg.QLabel('Mins:')
        secs_label = qg.QLabel('Secs:')
        ttl_time = self.dirs.settings.ttl_time
        self.mins_entry = GuiIntOnlyEntry(max_digits=2, default_text=format_secs(ttl_time, MINS))
        self.secs_entry = GuiIntOnlyEntry(max_digits=2, default_text=format_secs(ttl_time, SECS))
        self.mins_entry.setMaximumSize(self.sizeHint())
        self.set_time_btn = qg.QPushButton('Set Time')
        self.set_time_btn.clicked.connect(self.set_ttl_time)
        frame.addWidget(mins_label, 0, 0)
        frame.addWidget(secs_label, 0, 2)
        frame.addWidget(self.mins_entry, 0, 1)
        frame.addWidget(self.secs_entry, 0, 3)
        frame.addWidget(self.set_time_btn, 1, 0, 1, 4)

    def render_saving(self):
        """Creates a widget for choosing output save dir, and creating preset profiles"""
        frame = GuiSimpleFrame('Set Save Directory')
        self.grid.addWidget(frame, 3, 0, 1, 2)
        self.dir_label = qg.QLabel('')
        self.get_dir_btn = qg.QPushButton('Choose Save Directory')
        self.set_dirs_label()
        self.get_dir_btn.clicked.connect(self.set_directory)
        frame.addWidget(self.dir_label)
        frame.addWidget(self.get_dir_btn)

    # Start/Stop/Naming functions
    def targ_region_selected(self, selected):
        """We allow use of the start/stop button only if a target region is selected"""
        self.start_btn.setEnabled(selected)
        if selected:
            self.start_btn.toggle_state('START')
        else:
            self.start_btn.toggle_state('default')

    def get_trial_name(self):
        """Gets trial name from entry; if not valid, do not proceed"""
        name = str(self.name_entry.text().strip())
        # Replace forbidden characters that cannot be used in file names
        for char in name:
            if char in FORBIDDEN_CHARS:
                name = name.replace(char, '_')
        # Check name is not empty and has not been used
        if not name or name in self.dirs.list_file_names():
            self.name_entry.visual_warning()
            return False
        return name

    def run_experiment(self):
        """Starts or stops the experiment"""
        if self.start_btn.text() == 'START':
            name = self.get_trial_name()
            if not name:
                return
            # Check directories exist and create if not
            self.dirs.check_dirs()
            if not self.dirs.made_date_stamped_dir:
                self.dirs.create_date_stamped_dir()
            # Start Experiment
            directory = r'{}/[{}]'.format(self.dirs.date_stamped_dir, name)
            os.makedirs(directory)
            name = r'{}/[{}]'.format(directory, name)
            duration = self.dirs.settings.ttl_time
            params = name, duration
            self.expStartedSignal.emit(True, params)
        elif self.start_btn.text() == 'STOP':
            self.expStartedSignal.emit(False, (None, None))

    # Set time functions
    def set_ttl_time(self):
        """Get total time and send to recording processes"""
        mins = self.mins_entry.text().strip()
        secs = self.secs_entry.text().strip()
        mins = abs(int(mins)) if mins else 0
        secs = abs(int(secs)) if secs else 0
        ttl_time = float(mins * 60 + secs)
        ttl_time = ttl_time if ttl_time >= 30.0 else 30.0
        self.mins_entry.setText(format_secs(ttl_time, MINS))
        self.secs_entry.setText(format_secs(ttl_time, SECS))
        # Save, send to relevant processes.
        self.dirs.settings.ttl_time = ttl_time
        msg = NewMessage(cmd=CMD_SET_TIME, val=ttl_time)
        self.output_msgs.put_nowait(msg)

    # Set directory functions
    def set_dirs_label(self):
        """Show current save directory on a label"""
        directory = self.dirs.settings.last_save_dir
        if 'Desktop' in directory:
            directory = directory[directory.index('Desktop') - 1:]
        max_len = 30
        lines = []
        curr_line = ''
        for pathname in [name for name in directory.split('\\')]:
            if not len(curr_line) == 0:
                curr_line += '\\'
            if len(curr_line + pathname) <= max_len:
                curr_line += pathname
            else:
                lines.append(curr_line)
                curr_line = pathname
        lines.append(curr_line)
        directory = '\n'.join([''.join(line) for line in lines])
        self.dir_label.setText(directory)

    def set_directory(self):
        """Set the location save files are sent to"""
        directory = str(qg.QFileDialog.getExistingDirectory(None, 'Select Directory',
                                                            self.dirs.settings.last_save_dir))
        if not directory:
            return
        self.dirs.settings.last_save_dir = directory
        self.set_dirs_label()
        self.dirs.made_date_stamped_dir = False


# Widgets not included in MainControls manager
class GuiVideoOperations(qg.QWidget):
    """Buttons for the following functions:
    - Toggle Use Camera
    - Toggle Video Source
    - Clear Heatmap / Pathing map
    - Calibrate Background
    - Get Bounding Coordinates
    - Toggle Cropping"""
    def __init__(self, dirs):
        super(GuiVideoOperations, self).__init__()
        self.dirs = dirs
        self.is_enabled = True
        self.output_msgs = PROC_HANDLER_QUEUE
        self.init_btns()

    def set_enabled(self, enable):
        for w in [self.bounds_frm, self.manual_frm, self.recalib_frm, self.vidsrc_frm]:
            w.setEnabled(enable)
        self.is_enabled = enable

    def init_btns(self):
        """Setup all buttons and add to grid"""
        self.use_cmr_btn = qg.QPushButton('Use Camera')
        self.use_vid_btn = qg.QPushButton('Use Recorded Video')
        self.clr_maps_btn = qg.QPushButton('Reset Pathing and Heatmap')
        self.get_bg_btn = qg.QPushButton('Recalibrate Background')
        self.reset_bnds_btn = qg.QPushButton('Reset Bounds')
        self.get_bnds_btn = GuiFlipBtn(default_msg='Set Tracking Boundaries',
                                       flipped_msg='Cancel',
                                       default_color='', flipped_color=qBgRed)
        self.flip_crop_btn = GuiFlipBtn(default_msg='Show Tracked Image Only',
                                        flipped_msg='Show Full Image')
        self.flip_crop_btn.permit_use = False if self.dirs.settings.bounding_coords == DEFAULT_BOUNDS else True
        self.flip_crop_btn.setEnabled(self.flip_crop_btn.permit_use)
        self.enable_manual_btn = GuiFlipBtn(default_msg='Turn On Manual Mode', default_color=qBgCyan,
                                            flipped_msg='Turn Off Manual Mode', flipped_color=qBgOrange)
        self.send_stim_btn = qg.QPushButton('Send Stimulus')
        self.send_stim_btn.setEnabled(False)
        # Gridding
        self.recalib_frm = GuiSimpleFrame('Calibrate Video')
        self.vidsrc_frm = GuiSimpleFrame('Video Source')
        self.bounds_frm = GuiSimpleFrame('Create Bounds')
        self.manual_frm = GuiSimpleFrame('Manual Mode')
        self.recalib_frm.addWidget(self.clr_maps_btn)
        self.recalib_frm.addWidget(self.get_bg_btn)
        self.vidsrc_frm.addWidget(self.use_cmr_btn)
        self.vidsrc_frm.addWidget(self.use_vid_btn)
        self.bounds_frm.addWidget(self.reset_bnds_btn, 0, 0)
        self.bounds_frm.addWidget(self.get_bnds_btn, 0, 1, 1, 2)
        self.bounds_frm.addWidget(self.flip_crop_btn, 1, 0, 1, 3)
        self.manual_frm.addWidget(self.enable_manual_btn)
        self.manual_frm.addWidget(self.send_stim_btn)
        # Internal signal/slot connecting
        self.flip_crop_btn.clicked.connect(self.toggle_show_cropped)
        self.get_bnds_btn.clicked.connect(self.enable_disable_btns)
        self.use_vid_btn.clicked.connect(lambda: self.toggle_vid_src(get_fname=True))
        self.use_cmr_btn.clicked.connect(lambda: self.toggle_vid_src(get_fname=False))
        self.get_bg_btn.clicked.connect(lambda: self.send_message(cmd=CMD_GET_BG))
        self.clr_maps_btn.clicked.connect(lambda: self.send_message(cmd=CMD_CLR_MAPS))
        self.reset_bnds_btn.clicked.connect(self.disable_flip_crop_btn)
        self.enable_manual_btn.clicked.connect(self.toggle_manual_mode)
        self.send_stim_btn.clicked.connect(self.send_stimulus)

    def send_message(self, cmd=None, val=None):
        """Sends a message to process handler"""
        msg = NewMessage(cmd=cmd, val=val)
        self.output_msgs.put_nowait(msg)

    def toggle_show_cropped(self):
        """Inform CV2 Process to show cropped image or not"""
        self.flip_crop_btn.toggle_state()
        self.send_message(cmd=CMD_SHOW_TRACKED)

    def got_new_bounds(self, bounds):
        """Checks if new bounds are different from default, and enables use of flip crop btn"""
        if bounds != DEFAULT_BOUNDS:
            self.flip_crop_btn.permit_use = True
        else:
            self.flip_crop_btn.permit_use = False
        self.enable_disable_btns()

    def enable_disable_btns(self):
        """Enable/Disable widgets depending on if getting bounds"""
        for widget in self.recalib_frm, self.vidsrc_frm, self.manual_frm:
            widget.setEnabled(not widget.isEnabled())
        self.reset_bnds_btn.setEnabled(not self.reset_bnds_btn.isEnabled())
        if self.flip_crop_btn.permit_use:
            self.flip_crop_btn.setEnabled(not self.flip_crop_btn.isEnabled())
        self.get_bnds_btn.toggle_state()

    def disable_flip_crop_btn(self):
        """disables this button"""
        self.flip_crop_btn.permit_use = False
        self.flip_crop_btn.setEnabled(False)

    def toggle_vid_src(self, get_fname):
        """Change video source"""
        if get_fname:
            fname = qg.QFileDialog.getOpenFileName(self, 'Choose Video Source', self.dirs.settings.last_save_dir)
            if fname == '':
                return  # cancel
        else:
            fname = ''
        self.send_message(cmd=CMD_SET_VIDSRC, val=fname)

    def toggle_manual_mode(self):
        """Turns manual mode on or off"""
        self.enable_manual_btn.toggle_state()
        self.send_message(cmd=CMD_TOGGLE_MANUAL_TRIGGER)
        self.send_stim_btn.setEnabled(not self.send_stim_btn.isEnabled())

    def send_stimulus(self):
        """Sends a manual stimulus to arduino"""
        self.send_message(cmd=CMD_SEND_STIMULUS)
