# coding=utf-8

"""Interactive display that allows picking a point as target perim center"""

import PyQt4.QtGui as qg
import PyQt4.QtCore as qc
from Misc.GlobalVars import *
from DirsSettings.Settings import SingleTargetArea
from Misc.CustomClasses import NewMessage
from GUI.DataDisplays.SendRecvProtocols import PixmapWithArray


# Custom Objects
class GuiTargetAreaIndicator(qg.QGraphicsEllipseItem):
    """A circle that indicates where target areas are"""
    def __init__(self, scene, data, radius=3):
        super(GuiTargetAreaIndicator, self).__init__(scene=scene)
        self.radius = radius
        self.setPen(qBlack)
        self.setBrush(qYellow)
        self.set_data(data)
        self.set_rect()

    def set_data(self, data):
        """provide new data to this indicator"""
        self.x = data.x
        self.y = data.y

    def set_rect(self):
        """Scales coordinates into new rectangle"""
        self.setRect(self.x - self.radius, self.y - self.radius, self.radius * 2, self.radius * 2)


class GuiBoundingRectGetter(qg.QGraphicsRectItem):
    """Finds and returns user defined bounding coords"""
    def __init__(self, scene, signal):
        super(GuiBoundingRectGetter, self).__init__(0, 0, VID_DIM[1], VID_DIM[0], scene=scene)
        self.setPen(qClear)
        self.setBrush(qClear)
        self.setZValue(2)
        self.signal = signal
        self.bounding_coords = []

    def mousePressEvent(self, e):
        """Capture mouse clicks to get bounding coordinates"""
        if len(self.bounding_coords) < 2:
            self.bounding_coords.append((e.pos().x(), e.pos().y()))
        if len(self.bounding_coords) == 2:
            # get topleft and bottom right
            x1, y1 = self.bounding_coords[0]
            x2, y2 = self.bounding_coords[1]
            x1, x2 = min((x1, x2)), max((x1, x2))
            y1, y2 = min((y1, y2)), max((y1, y2))
            self.bounding_coords = [(int(x1), int(y1)), (int(x2), int(y2))]
            # Send to Parent Display
            self.signal.emit(self.bounding_coords)
            self.bounding_coords = []


class GuiTargCenterGetter(qg.QGraphicsRectItem):
    """Returns user defined target center location"""
    def __init__(self, scene, signal):
        super(GuiTargCenterGetter, self).__init__(0, 0, VID_DIM[1], VID_DIM[0], scene=scene)
        self.setPen(qClear)
        self.setBrush(qClear)
        self.setZValue(2)
        self.signal = signal

    def mousePressEvent(self, e):
        """Capture mouse click to get location of targ center"""
        pos = e.pos()
        self.signal.emit((int(pos.x()), int(pos.y())))


# Main Display
class GuiInteractiveDisplay(qg.QGraphicsView):
    """Mouse Interactive graphics interface. Shows images from QPixmap"""
    boundsSetSignal = qc.pyqtSignal(list)
    targLocSetSignal = qc.pyqtSignal(tuple)

    def __init__(self, dirs, cv2_gui_mp_array, update_interval_ms):
        super(GuiInteractiveDisplay, self).__init__()
        self.dirs = dirs
        self.output_msgs = PROC_HANDLER_QUEUE
        # Tracking Boundaries
        self.creating_bounds = False
        self.bounding_coords = self.dirs.settings.bounding_coords
        # Target Center
        self.getting_targ_center = False
        # Scene
        self.scene = qg.QGraphicsScene()
        self.setScene(self.scene)
        # Basic Dims
        self.setMinimumSize(642, 482)
        self.setMaximumSize(642, 482)
        self.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        # Init Objects and Timers
        self.init_scene_objs(cv2_gui_mp_array)
        self.init_update_timer(update_interval_ms)

    def init_scene_objs(self, cv2_gui_mp_array):
        """Set up objects and add to scene"""
        # Main Pixmap
        self.cv2img = PixmapWithArray(self.scene, cv2_gui_mp_array)
        # Indicators
        self.targ_center_indicator = GuiTargetAreaIndicator(self.scene,
                                                            self.dirs.settings.last_targ_areas.areas[0])
        self.draw_cv2_targ_area(draw=True)
        # Bounds Getter
        self.bounds_getter = GuiBoundingRectGetter(self.scene, self.boundsSetSignal)
        self.bounds_getter.hide()
        # Targ Center Getter
        self.targ_getter = GuiTargCenterGetter(self.scene, self.targLocSetSignal)
        self.targ_getter.hide()
        # Connect Signals
        self.connect_child_signals()

    def init_update_timer(self, update_interval_ms):
        """Refreshes camera display"""
        timer = qc.QTimer(self)
        timer.timeout.connect(self.cv2img.update_display)
        timer.start(update_interval_ms)

    # pyqtSignal Handling
    def connect_child_signals(self):
        """Sets up internal signals. For the same signal, order of connection = order of calling when signal emits"""
        self.boundsSetSignal.connect(self.recv_new_bounds)
        # When clicking a target indicator
        self.targLocSetSignal.connect(self.recv_new_targ_loc)

    # Communicating with Proc Handler
    def msg_proch(self, cmd=None, val=None):
        """Sends messages to process handler"""
        msg = NewMessage(cmd=cmd, val=val)
        self.output_msgs.put_nowait(msg)

    def draw_cv2_targ_area(self, draw):
        """notify cv2 proc to draw target perimeter"""
        if draw:
            radius = self.dirs.settings.target_area_radius
            center = self.targ_center_indicator.x, self.targ_center_indicator.y
            self.msg_proch(cmd=CMD_TARG_DRAW, val=(center, radius))
        else:
            self.msg_proch(cmd=CMD_TARG_DRAW, val=None)

    # Get new target center coordinate
    def get_new_targ_loc(self):
        """Gets coordinates for target center"""
        if not self.getting_targ_center:
            self.getting_targ_center = True
            self.targ_center_indicator.hide()
            self.targ_getter.show()
            self.draw_cv2_targ_area(draw=False)
        else:
            self.getting_targ_center = False
            self.targ_center_indicator.show()
            self.targ_getter.hide()
            self.draw_cv2_targ_area(draw=True)

    def recv_new_targ_loc(self, loc):
        """Process new location"""
        self.dirs.settings.last_targ_areas.areas[0].x = loc[0]
        self.dirs.settings.last_targ_areas.areas[0].y = loc[1]
        self.targ_center_indicator.set_data(self.dirs.settings.last_targ_areas.areas[0])
        self.targ_center_indicator.set_rect()
        self.targ_center_indicator.show()
        self.targ_getter.hide()
        self.draw_cv2_targ_area(draw=True)
        self.getting_targ_center = False

    # Bounding Coordinates Creation
    def create_new_bounds(self):
        """Create boundaries that we track within and ignore outside portions of img. Can cancel"""
        self.bounds_getter.bounding_coords = []
        if not self.creating_bounds:
            self.creating_bounds = True
            self.targ_center_indicator.hide()
            self.bounds_getter.show()
            self.draw_cv2_targ_area(draw=False)
            self.msg_proch(cmd=CMD_SET_BOUNDS, val=None)
        elif self.creating_bounds:
            self.creating_bounds = False
            self.targ_center_indicator.show()
            self.bounds_getter.hide()
            self.draw_cv2_targ_area(draw=True)
            self.msg_proch(cmd=CMD_SET_BOUNDS,
                           val=None if self.bounding_coords == DEFAULT_BOUNDS else self.bounding_coords)

    def recv_new_bounds(self, bounding_coords):
        """Process new bounding coordinates"""
        self.bounding_coords = bounding_coords
        self.dirs.settings.bounding_coords = bounding_coords
        self.targ_center_indicator.show()
        self.bounds_getter.hide()
        self.draw_cv2_targ_area(draw=True)
        self.msg_proch(cmd=CMD_SET_BOUNDS, val=None if bounding_coords == DEFAULT_BOUNDS else bounding_coords)
        self.creating_bounds = False
