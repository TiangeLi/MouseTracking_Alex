# coding=utf-8

"""Contains all Data Display widgets"""

import PyQt4.QtGui as qg
import PyQt4.QtCore as qc
from Misc.GlobalVars import VID_DIM
from GUI.DataDisplays.InteractiveDisplay import GuiInteractiveDisplay
from GUI.DataDisplays.SendRecvProtocols import LabelWithArray, PixmapWithArray


class GuiProgressBarDisplay(qg.QGraphicsView):
    """Displays progress bar; progress bar generated in Coords processor"""
    def __init__(self, mp_array, update_interval_ms):
        super(GuiProgressBarDisplay, self).__init__()
        self.scene = qg.QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap = PixmapWithArray(self.scene, mp_array=mp_array)
        shape = self.pixmap.np_array.shape
        self.setMinimumSize(shape[1]+2, shape[0]+2)
        self.setMaximumSize(shape[1]+2, shape[0]+2)
        timer = qc.QTimer(self)
        timer.timeout.connect(self.pixmap.update_display)
        timer.start(update_interval_ms)


class DataDisplays(qg.QGroupBox):
    """Container for data displays"""
    def __init__(self, dirs):
        super(DataDisplays, self).__init__()
        self.dirs = dirs
        self.grid = qg.QGridLayout()
        self.setLayout(self.grid)

    def render_widgets(self, cv2gui_mp_array, heatmap_mp_array,
                       pathing_mp_array, gradient_mp_array, progbar_mp_array):
        """Generate and add widgets to grid"""
        self.cmr_disp = GuiInteractiveDisplay(self.dirs, cv2gui_mp_array, update_interval_ms=5)
        pathing = LabelWithArray(pathing_mp_array, update_interval_ms=5)
        heatmap = LabelWithArray(heatmap_mp_array, update_interval_ms=5)
        gradient = LabelWithArray(gradient_mp_array, update_interval_ms=5)
        progbar = GuiProgressBarDisplay(progbar_mp_array, update_interval_ms=5)
        # Add to Grid
        self.grid.addWidget(pathing, 0, 0)
        self.grid.addWidget(heatmap, 1, 0)
        self.grid.addWidget(gradient, 2, 0)
        self.grid.addWidget(self.cmr_disp, 0, 1, 2, 1)
        self.grid.addWidget(progbar, 2, 1)
        self.grid.setHorizontalSpacing(1)
        self.grid.setVerticalSpacing(1)
