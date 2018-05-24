# coding=utf-8

"""Mouse Tracking and Stimulation"""

import sys
import time
from DirsSettings.Directories import Directories
from Concurrency.CV2Proc import CV2Processor
from Concurrency.CmrProc import CameraHandler
from Concurrency.CoordsProc import CoordinateProcessor
from Concurrency.MainHandler import ProcessHandler
from Concurrency.VidRecProc import VideoRecorder, CV2VideoRecorder
from GUI.DataDisplays.MainContainer import DataDisplays
from GUI.UserControls.ExpControls import GuiVideoOperations, GuiMainControls
from Misc.GlobalVars import *
from Misc.CustomClasses import NewMessage, ReadMessage
from Misc.CustomFunctions import clear_console
import queue as Queue


class MasterGui(qg.QWidget):
    """Main GUI Window"""
    def __init__(self, dirs):
        super(MasterGui, self).__init__()
        self.dirs = dirs
        self.setWindowTitle('Mouse Tracking')
        self.setWindowIcon(qg.QIcon('favicon.ico'))
        # Concurrency
        self.proc_handler_queue = PROC_HANDLER_QUEUE
        self.master_dump_queue = MASTER_DUMP_QUEUE
        self.create_processes()
        self.create_msg_parser()
        self.set_msg_polling_timer()
        # Layout and Signals
        self.render_widgets()
        self.connect_signals()
        self.initialize_widgets()
        # Experiment Running?
        self.exp_running = False
        # Can we exit program safely?
        self.ready_to_exit = False
        # Finalize
        size = self.sizeHint()
        self.setMaximumSize(size)
        self.setMinimumSize(size)
        self.setFocusPolicy(qc.Qt.StrongFocus)
        self.show()

    def create_processes(self):
        """Generate child processes that take over various backend tasks"""
        self.cv2_proc = CV2Processor(saved_bounds=self.dirs.settings.bounding_coords)
        self.cmr_proc = CameraHandler(self.cv2_proc.cmrcv2_mp_array)
        self.coord_proc = CoordinateProcessor(self.cv2_proc.coords_output_queue,
                                              self.dirs.settings.ttl_time)
        self.cmr_vidrec_proc = VideoRecorder(name=PROC_CMR_VIDREC, is_color=False,
                                             file_name_ending='_RAW.avi',
                                             mp_array=self.cmr_proc.cmr_cv2_mp_array,
                                             recording_sync=self.cmr_proc.rec_to_file_sync_event)
        self.cv2_vidrec_proc = CV2VideoRecorder(name=PROC_CV2_VIDREC, is_color=True,
                                                file_name_ending='_CV2.avi',
                                                recording_sync=self.cv2_proc.rec_to_file_sync_event,
                                                pathing=self.coord_proc.pathing.mp_array,
                                                heatmap=self.coord_proc.heatmap.mp_array,
                                                gradient=self.coord_proc.gradient.mp_array,
                                                progbar=self.coord_proc.progbar.mp_array,
                                                cv2gui=self.cv2_proc.cv2gui_mp_array)
        # Main handler for children
        self.proc_handler = ProcessHandler(self.cmr_proc.input_msgs,
                                           self.cv2_proc.input_msgs,
                                           self.coord_proc.input_msgs,
                                           self.cmr_vidrec_proc.input_msgs,
                                           self.cv2_vidrec_proc.input_msgs,
                                           # Message receipt pipes
                                           self.coord_proc.parent_pipe,
                                           self.cmr_vidrec_proc.parent_pipe,
                                           self.cv2_vidrec_proc.parent_pipe)
        # Start processes
        self.cmr_proc.start()
        self.cv2_proc.start()
        self.coord_proc.start()
        self.cmr_vidrec_proc.start()
        self.cv2_vidrec_proc.start()
        self.proc_handler.start()

    def render_widgets(self):
        """Add widgets to main window"""
        # Grid
        self.grid = qg.QGridLayout()
        self.setLayout(self.grid)
        # Widgets
        self.data_displays = DataDisplays(self.dirs)
        self.data_displays.render_widgets(cv2gui_mp_array=self.cv2_proc.cv2gui_mp_array,
                                          heatmap_mp_array=self.coord_proc.heatmap.mp_array,
                                          pathing_mp_array=self.coord_proc.pathing.mp_array,
                                          gradient_mp_array=self.coord_proc.gradient.mp_array,
                                          progbar_mp_array=self.coord_proc.progbar.mp_array)
        self.vid_cntrls = GuiVideoOperations(self.dirs)
        self.exp_cntrls = GuiMainControls(self.dirs)
        # Connect Signals
        # Add to Grid
        self.grid.addWidget(self.vid_cntrls.recalib_frm, 0, 0)
        self.grid.addWidget(self.vid_cntrls.vidsrc_frm, 0, 1)
        self.grid.addWidget(self.vid_cntrls.bounds_frm, 0, 2)
        self.grid.addWidget(self.vid_cntrls.manual_frm, 0, 3)
        self.grid.addWidget(self.data_displays, 1, 0, 1, 4)
        self.grid.addWidget(self.exp_cntrls, 0, 4, 2, 1)

    def connect_signals(self):
        """Connect signals to slots in separate child widgets"""
        # Video Controls (Top left rows)
        self.vid_cntrls.get_bnds_btn.clicked.\
            connect(lambda: self.exp_cntrls.setEnabled(not self.exp_cntrls.isEnabled()))
        self.vid_cntrls.get_bnds_btn.clicked.\
            connect(self.data_displays.cmr_disp.create_new_bounds)
        self.vid_cntrls.reset_bnds_btn.clicked.\
            connect(lambda: self.data_displays.cmr_disp.recv_new_bounds(DEFAULT_BOUNDS))
        # Interactive Display Controls (main camera widget)
        self.data_displays.cmr_disp.boundsSetSignal.\
            connect(self.vid_cntrls.got_new_bounds)
        self.data_displays.cmr_disp.boundsSetSignal.\
            connect(lambda: self.exp_cntrls.setEnabled(not self.exp_cntrls.isEnabled()))
        self.data_displays.cmr_disp.indicators.targToggledSignal.\
            connect(self.exp_cntrls.targ_area_config.load_from_data)
        self.data_displays.cmr_disp.indicators.targReshapedSignal.\
            connect(self.exp_cntrls.targ_area_config.indicators_reshaped)
        self.data_displays.cmr_disp.indicators.enableStartSignal.\
            connect(self.exp_cntrls.curr_exp_config.targ_region_selected)
        # Main controls
        self.exp_cntrls.targ_area_config.newTargAreasSignal.\
            connect(self.data_displays.cmr_disp.reset_targ_region_inds)
        self.exp_cntrls.curr_exp_config.expStartedSignal.\
            connect(self.run_experiment)

    def initialize_widgets(self):
        """After connecting signals, some widgets need further initialization"""
        self.data_displays.cmr_disp.indicators.reshape_indicators()

    def run_experiment(self, run_exp, trial_params):
        """Triggered by start button signal. Sends recording signal to Recording process, and enable/disable widgets"""
        # Enable/Disable widgets while experiment running
        if run_exp:
            self.exp_running = True
            self.vid_cntrls.bounds_frm.setEnabled(False)
            self.vid_cntrls.vidsrc_frm.setEnabled(False)
            self.vid_cntrls.recalib_frm.setEnabled(False)
            self.data_displays.cmr_disp.setEnabled(False)
            self.exp_cntrls.targ_area_config.setEnabled(False)
            self.data_displays.cmr_disp.indicators.hide_objs()
            self.data_displays.cmr_disp.indicators.targ_area_highlight.hide()
            self.exp_cntrls.curr_exp_config.name_entry.setEnabled(False)
            self.exp_cntrls.curr_exp_config.start_btn.setEnabled(False)
            self.send_message(cmd=CMD_START, val=trial_params)
        else:
            self.send_message(cmd=CMD_STOP)

    def experiment_started(self):
        """this is run when exp_start_event has been set by Proc_handler,
        i.e. all widgets and processes are in run_experiment state"""
        self.exp_cntrls.curr_exp_config.start_btn.setEnabled(True)
        self.exp_cntrls.curr_exp_config.start_btn.toggle_state('STOP')

    def experiment_finished(self, saving):
        """This runs when the experiment is finished"""
        # output files/videos are still finishing saving
        if saving:
            self.exp_cntrls.curr_exp_config.start_btn.setEnabled(False)
            self.exp_cntrls.curr_exp_config.start_btn.toggle_state('SAVING_VIDEOS')
        else:
            self.vid_cntrls.bounds_frm.setEnabled(True)
            self.vid_cntrls.vidsrc_frm.setEnabled(True)
            self.vid_cntrls.recalib_frm.setEnabled(True)
            self.data_displays.cmr_disp.setEnabled(True)
            self.exp_cntrls.targ_area_config.setEnabled(True)
            self.data_displays.cmr_disp.indicators.show_objs()
            self.data_displays.cmr_disp.indicators.targ_area_highlight.show()
            self.exp_cntrls.curr_exp_config.name_entry.setEnabled(True)
            self.exp_cntrls.curr_exp_config.start_btn.setEnabled(True)
            self.exp_cntrls.curr_exp_config.start_btn.toggle_state('START')
            self.exp_running = False
            print('Finished Experiment')

    # Communication with proc handler
    def send_message(self, dev=None, cmd=None, val=None):
        """Sends a message to process handler"""
        msg = NewMessage(dev=dev, cmd=cmd, val=val)
        self.proc_handler_queue.put_nowait(msg)

    def msg_polling(self):
        """Polls for messages in master dump queue"""
        try:
            msg = self.master_dump_queue.get_nowait()
        except Queue.Empty:
            pass
        else:
            msg = ReadMessage(msg)
            self.msg_parser[msg.command]()

    def create_msg_parser(self):
        self.msg_parser = {
            MSG_STARTED: self.experiment_started,
            MSG_VIDREC_SAVING: lambda: self.experiment_finished(saving=True),
            MSG_VIDREC_FINISHED: lambda: self.experiment_finished(saving=False),
        }

    def set_msg_polling_timer(self):
        """Create a GUI timer that periodically checks for new messages from queue"""
        timer = qc.QTimer(self)
        timer.timeout.connect(self.msg_polling)
        timer.start(10)

    # Delete user saves. USE FOR DEBUG ONLY!
    def keyPressEvent(self, event):
        """Adds Keyboard Shortcuts for certain operations"""
        # Combo: Alt+Cntrl+Shift+K
        # Function: DELETES ALL FILES. USE FOR DEBUG ONLY
        if event.key() == qKey_k and event.modifiers() & qMod_shift \
                and event.modifiers() & qMod_cntrl and event.modifiers() & qMod_alt:
            self.nuke_files()

    def nuke_files(self):
        """DEBUG ONLY"""
        if self.exp_running:
            return
        msg = 'You are about to delete all user settings!\n\nContinue anyway?'
        nuke = qg.QMessageBox.warning(self, 'WARNING', msg, qg.QMessageBox.No | qg.QMessageBox.Yes, qg.QMessageBox.No)
        if nuke == qg.QMessageBox.Yes:
            print('Exiting...')
            self.dirs.del_all = True
            self.close()

    # Custom Close implementation
    def closeEvent(self, e):
        """We exit iff experiment is not running. We also wait until all processes have exited"""
        e.ignore()
        if self.exp_running:
            qg.QMessageBox.warning(self, 'Warning!', 'Cannot Close While Experiment is Running!', qg.QMessageBox.Close)
            return
        else:
            self.send_message(cmd=CMD_EXIT)
            print('---------------------------------------------')
            start_time = time.perf_counter()
            while not (len(mp.active_children()) == 0) and not (time.perf_counter()-start_time > 5):
                time.sleep(5.0 / 1000.0)
            super(MasterGui, self).closeEvent(e)
            if len(mp.active_children()) != 0:
                print('--- Unable to Close All Child Processes ---')
            else:
                print('All Child Processes Closed')


# Main Program
if __name__ == '__main__':
    clear_console()
    print('Starting Mouse Tracker 1.0\n\n')
    # Freeze Support if we create a windows .exe
    mp.freeze_support()
    # Setup Directories and save files
    DIRS = Directories()
    # Start GUI App
    app = qg.QApplication(sys.argv)
    window = MasterGui(DIRS)
    app.exec_()
    # On Exit, save user settings to file
    if DIRS.save_on_exit:
        DIRS.save()
    if DIRS.del_all:
        DIRS.nuke_files()
    # Safely Exi App and Python
    print('Active Processes:', mp.active_children())
    sys.exit()
