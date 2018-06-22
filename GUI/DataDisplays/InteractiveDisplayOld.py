# coding=utf-8

"""Interactive Video Feed Display Objects; with old implementation"""

from collections import deque
import PyQt4.QtGui as qg
import PyQt4.QtCore as qc
from Misc.GlobalVars import *
from Misc.CustomClasses import *
from DirsSettings.Settings import SingleTargetArea
from GUI.DataDisplays.SendRecvProtocols import PixmapWithArray
from time import sleep


# Custom QGraphics Objects
class GuiQuadrantIndicator(qg.QGraphicsRectItem):
    """Shows a single quadrant"""
    def __init__(self, scene, quadrant, clicked_signal, move_signal, zval_selected, zval_unselected):
        super(GuiQuadrantIndicator, self).__init__(scene=scene)
        self.quadrant = quadrant
        self.clickedSignal = clicked_signal
        self.moveSignal = move_signal
        self.selected = False
        self.zval_selected = zval_selected
        self.zval_unselected = zval_unselected
        self.setZValue(zval_unselected)
        self.setAcceptHoverEvents(True)
        self.setPen(qClear)

    def set_rect(self, x1, y1, x2, y2):
        """Sets shape of indicator"""
        self.setRect(x1, y1, x2-x1, y2-y1)

    def set_outlines(self):
        """Change outlines and brush depending on selection state"""
        if not self.selected:
            self.setPen(qClear)
            self.setZValue(self.zval_unselected)
        else:
            self.setPen(qWhite)
            self.setBrush(qClear)
            self.setZValue(self.zval_selected)

    def hoverMoveEvent(self, e):
        """Tracks mouse within rect"""
        if self.selected:
            loc = e.pos()
            self.moveSignal.emit(int(loc.x()), int(loc.y()), True)

    def hoverEnterEvent(self, e):
        """Change color of indicator when mouse enters"""
        if not self.selected:
            self.setBrush(qSemi)

    def hoverLeaveEvent(self, e):
        """Change color of indicator when mouse leaves"""
        if not self.selected:
            self.setBrush(qClear)
        else:
            self.moveSignal.emit(0, 0, False)

    def mousePressEvent(self, e):
        """Signal that this quadrant was clicked"""
        self.clickedSignal.emit(self.quadrant)


class GuiTargetAreaIndicator(qg.QGraphicsEllipseItem):
    """A clickbale circle that indicates where target areas are"""
    def __init__(self, scene, data, signal, zval, radius=4):
        super(GuiTargetAreaIndicator, self).__init__(scene=scene)
        self.setZValue(zval)
        self.signal = signal
        self.radius = radius
        self.setPen(qBlack)
        self.set_data(data)

    def set_data(self, data):
        """provide new data to this indicator"""
        self.selected = False
        self.data = data
        # Drawing Params
        self.x = None
        self.y = None
        if self.data.tested:
            self.setBrush(qWhite)
        else:
            self.setBrush(qYellow)

    def set_rect(self, x1, y1, x2, y2):
        """Scales coordinates into new rectangle"""
        xscale = x2 - x1
        xshift = x1
        yscale = y2 - y1
        yshift = y1
        self.x = int((self.data.x * xscale) + xshift)
        self.y = int((self.data.y * yscale) + yshift)
        self.setRect(self.x - self.radius, self.y - self.radius, self.radius * 2, self.radius * 2)
        print(self.x, self.y)

    def set_color(self):
        """Set colors if selected"""
        if self.selected:
            self.setBrush(qBlue)
        else:
            if self.data.tested:
                self.setBrush(qWhite)
            else:
                self.setBrush(qYellow)

    def mousePressEvent(self, e):
        """Signal that this object was clicked"""
        self.signal.emit(self.data)


class GuiTargetAreaHighlight(qg.QGraphicsRectItem):
    """A Highlight for currently hovered target region"""
    def __init__(self, scene, signal, zval):
        super(GuiTargetAreaHighlight, self).__init__(scene=scene)
        self.data = None
        self.signal = signal
        self.setBrush(qSemi)
        self.setPen(qWhite)
        self.setZValue(zval)

    def set_rect(self, x, y, radius):
        """Sets bounding rect"""
        self.setRect(x-radius, y-radius, radius*2, radius*2)

    def mousePressEvent(self, e):
        """Signal that this object was clicked"""
        cntrl_pressed = False
        if e.modifiers() & qMod_cntrl:
            cntrl_pressed = True
        self.signal.emit(cntrl_pressed, self.data)


class GuiIndicatorManager(qg.QWidget):
    """Manages interactive indicators"""
    quadClickedSignal = qc.pyqtSignal(str)
    quadMouseMoveSignal = qc.pyqtSignal(int, int, bool)
    targClickedSignal = qc.pyqtSignal(bool, SingleTargetArea)
    targToggledSignal = qc.pyqtSignal(bool, SingleTargetArea)
    targReshapedSignal = qc.pyqtSignal(list)
    enableStartSignal = qc.pyqtSignal(bool)

    def __init__(self, scene, dirs, bounding_coords):
        super(GuiIndicatorManager, self).__init__()
        self.scene = scene
        self.dirs = dirs
        self.bounding_coords = bounding_coords
        self.quadrant_in_use = dirs.settings.last_quadrant
        self.quad_objs = deque()
        self.area_objs = deque()
        self.init_quadrant_inds()
        self.init_targ_area_inds()

    def init_quadrant_inds(self):
        """Setup quadrant indicators"""
        for quadrant in TOPLEFT, TOPRIGHT, BOTTOMLEFT, BOTTOMRIGHT:
            obj = GuiQuadrantIndicator(self.scene, quadrant, self.quadClickedSignal, self.quadMouseMoveSignal,
                                       zval_selected=0, zval_unselected=2)
            self.quad_objs.append(obj)

    def init_targ_area_inds(self):
        """Setup target area objects"""
        self.targ_area_highlight = GuiTargetAreaHighlight(self.scene, self.targClickedSignal, zval=1)
        for single_target_area in self.dirs.settings.last_targ_areas.areas:
            obj = GuiTargetAreaIndicator(self.scene, single_target_area, self.targClickedSignal, zval=3)
            self.area_objs.append(obj)

    def show_objs(self):
        """Shows objects on scene"""
        for item in (self.quad_objs + self.area_objs):
            item.show()

    def hide_objs(self):
        """Hides objects from scene"""
        for item in (self.quad_objs + self.area_objs):
            item.hide()

    def toggle_targ_inds(self, cntrl_key_pressed, data):
        """Toggles the target area indicators to selected/unselected"""
        if not data:
            data = SingleTargetArea(None, None, None, None)
        # Send data to other widgets that need it
        self.targToggledSignal.emit(cntrl_key_pressed, data)
        # Set targ area indicators
        selected = [obj for obj in self.area_objs if obj.selected]
        if not cntrl_key_pressed:
            if len(selected) > 1:
                for obj in selected:
                    obj.selected = False
            else:
                for obj in selected:
                    if obj.data != data:
                        obj.selected = False
        for obj in self.area_objs:
            if obj.data == data:
                obj.selected = not obj.selected
            obj.set_color()
        # Notify other widgets of selection state
        selected = [obj for obj in self.area_objs if obj.selected]
        self.enableStartSignal.emit(False if len(selected) != 1 else True)

    def reshape_indicators(self, new_bounding_coords=None, new_quadrant=None):
        """Set indicator shapes and locations"""
        if new_bounding_coords:
            self.bounding_coords = new_bounding_coords
        if new_quadrant:
            self.quadrant_in_use = new_quadrant
        x1, y1 = self.bounding_coords[0]
        x2, y2 = self.bounding_coords[1]
        xmid = (x1 + x2) / 2
        ymid = (y1 + y2) / 2
        quadrant_selector = {
            TOPLEFT: (x1, y1, xmid, ymid),
            TOPRIGHT: (xmid, y1, x2, ymid),
            BOTTOMLEFT: (x1, ymid, xmid, y2),
            BOTTOMRIGHT: (xmid, ymid, x2, y2),
        }
        # Rescale quadrants to bounding coords
        for obj in self.quad_objs:
            obj.set_rect(*quadrant_selector[obj.quadrant])
            if obj.quadrant == self.quadrant_in_use:
                obj.selected = True
            else:
                obj.selected = False
            obj.set_outlines()
        # Rescale target area indicators to bounding coords
        area_data = []
        for obj in self.area_objs:
            obj.set_rect(*quadrant_selector[self.quadrant_in_use])
            area_data.append((obj.x, obj.y, obj.data))
        self.targReshapedSignal.emit(area_data)

    def highlight_targ_area(self, x, y, show):
        """Highlights the entire target region we are hovering over"""
        if show:
            for obj in self.area_objs:
                if ((x - obj.x)**2 + (y - obj.y)**2) <= self.dirs.settings.target_area_radius ** 2:
                    self.targ_area_highlight.data = obj.data
                    radius = self.dirs.settings.target_area_radius
                    self.targ_area_highlight.set_rect(obj.x, obj.y, radius)
                    self.targ_area_highlight.show()
                    return
        self.targ_area_highlight.hide()


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
        self.signal.emit((pos.x(), pos.y()))


# Main Display
class GuiInteractiveDisplay(qg.QGraphicsView):
    """Mouse Interactive graphics interface. Shows images from QPixmap"""
    boundsSetSignal = qc.pyqtSignal(list)

    def __init__(self, dirs, cv2_gui_mp_array, update_interval_ms):
        super(GuiInteractiveDisplay, self).__init__()
        self.dirs = dirs
        self.output_msgs = PROC_HANDLER_QUEUE
        # Tracking Boundaries
        self.creating_bounds = False
        self.bounding_coords = self.dirs.settings.bounding_coords
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
        self.indicators = GuiIndicatorManager(self.scene, self.dirs, self.bounding_coords)
        # Bounds Getter
        self.bounds_getter = GuiBoundingRectGetter(self.scene, self.boundsSetSignal)
        self.bounds_getter.hide()
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
        # When clicking a quadrant
        self.indicators.quadClickedSignal.connect(self.update_quadrants)
        # When moving inside a quadrant
        self.indicators.quadMouseMoveSignal.connect(self.indicators.highlight_targ_area)
        # When clicking a target indicator
        self.indicators.targClickedSignal.connect(self.update_targ_areas)

    def update_quadrants(self, quadrant):
        """Update quadrant clicked and indicator shapes"""
        self.indicators.reshape_indicators(new_quadrant=quadrant)
        if quadrant != self.dirs.settings.last_quadrant:
            selected = [obj for obj in self.indicators.area_objs if obj.selected]
            if len(selected) == 1:
                radius = self.dirs.settings.target_area_radius
                obj = selected[0]
                scaled = obj.x, obj.y
                normalized = obj.data.x, obj.data.y
                self.msg_proch(cmd=CMD_TARG_DRAW, val=(scaled, normalized, radius))
        else:
            self.indicators.toggle_targ_inds(cntrl_key_pressed=False, data=None)
            self.msg_proch(cmd=CMD_TARG_DRAW, val=None)
        # Update backend user settings
        self.dirs.settings.last_quadrant = quadrant

    def update_targ_areas(self, cntrl, data):
        """Update targ indicators clicked and shapes"""
        self.indicators.toggle_targ_inds(cntrl_key_pressed=cntrl, data=data)
        selected = [obj for obj in self.indicators.area_objs if obj.selected]
        if len(selected) == 1:
            radius = self.dirs.settings.target_area_radius
            obj = selected[0]
            scaled = obj.x, obj.y
            normalized = obj.data.x, obj.data.y
            self.msg_proch(cmd=CMD_TARG_DRAW, val=(scaled, normalized, radius))
        else:
            self.msg_proch(cmd=CMD_TARG_DRAW, val=None)

    # Communicating with Proc Handler
    def msg_proch(self, cmd=None, val=None):
        """Sends messages to process handler"""
        msg = NewMessage(cmd=cmd, val=val)
        self.output_msgs.put_nowait(msg)

    # Bounding Coordinates Creation
    def create_new_bounds(self):
        """Create boundaries that we track within and ignore outside portions of img. Can cancel"""
        self.bounds_getter.bounding_coords = []
        if not self.creating_bounds:
            self.creating_bounds = True
            self.indicators.hide_objs()
            self.indicators.targ_area_highlight.hide()
            self.bounds_getter.show()
            self.msg_proch(cmd=CMD_SET_BOUNDS, val=None)
        elif self.creating_bounds:
            self.creating_bounds = False
            self.indicators.show_objs()
            self.bounds_getter.hide()
            self.msg_proch(cmd=CMD_SET_BOUNDS,
                           val=None if self.bounding_coords == DEFAULT_BOUNDS else self.bounding_coords)

    def recv_new_bounds(self, bounding_coords):
        """Process new bounding coordinates"""
        self.bounding_coords = bounding_coords
        self.dirs.settings.bounding_coords = bounding_coords
        self.indicators.reshape_indicators(new_bounding_coords=bounding_coords)
        self.indicators.show_objs()
        self.bounds_getter.hide()
        self.msg_proch(cmd=CMD_SET_BOUNDS, val=None if bounding_coords == DEFAULT_BOUNDS else bounding_coords)
        selected = [obj for obj in self.indicators.area_objs if obj.selected]
        if len(selected) == 1:
            radius = self.dirs.settings.target_area_radius
            obj = selected[0]
            scaled = obj.x, obj.y
            normalized = obj.data.x, obj.data.y
            self.msg_proch(cmd=CMD_TARG_DRAW, val=(scaled, normalized, radius))
        self.creating_bounds = False

    def reset_targ_region_inds(self):
        """reload target region data from save into indicators"""
        areas = (area for area in self.dirs.settings.last_targ_areas.areas)
        for obj in self.indicators.area_objs:
            obj.set_data(data=next(areas))
        self.indicators.reshape_indicators()
        self.msg_proch(cmd=CMD_TARG_DRAW, val=None)
