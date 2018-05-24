# coding=utf-8

"""Custom Implementations of various Qt Widgets"""

import PyQt4.QtGui as qg
import PyQt4.QtCore as qc
from Misc.GlobalVars import *


# Organization
class GuiSimpleGroup(qg.QGraphicsItemGroup):
    """Simplifies adding unnamed Qt items to a shared group"""
    def __init__(self, selectable=False):
        super(GuiSimpleGroup, self).__init__()
        if selectable:
            self.setFlag(qSelectable, enabled=True)

    def add(self, item, pos_x=None, pos_y=None, pen=None, brush=None, color=None, tooltip=None, selectable=False):
        """Adds a new item with specifiable attributes"""
        self.addToGroup(item)
        if pos_x and pos_y: item.setPos(pos_x, pos_y)
        if pen: item.setPen(pen)
        if brush: item.setBrush(brush)
        if color: item.setDefaultTextColor(color)
        if tooltip: item.setToolTip(tooltip)
        if selectable: item.setFlag(qSelectable, enabled=True)


class GuiSimpleFrame(qg.QGroupBox):
    """A Frame with name and grid"""
    def __init__(self, name):
        super(GuiSimpleFrame, self).__init__(name)
        self.grid = qg.QGridLayout()
        self.setLayout(self.grid)

    def addWidget(self, widget, *args):
        """Reimplement grid addWidget"""
        self.grid.addWidget(widget, *args)


# Custom Animation Objects
class GuiObjectWithAnim(object):
    """Object with Qt Animation Properties"""
    def __init__(self, parent_obj):
        self.parent_obj = parent_obj
        # Animation Boolean
        self.running = False

    def reset_timers_anims(self, duration):
        """Resets timers and animations with new durations"""
        # Timer
        self.timer = qc.QTimeLine(duration)
        self.timer.setCurveShape(qc.QTimeLine.LinearCurve)
        self.timer.setFrameRange(0, duration * 1000)
        # Animation Object
        self.anim = qg.QGraphicsItemAnimation()
        self.anim.setItem(self.parent_obj)
        self.anim.setTimeLine(self.timer)


class GuiTextWithAnim(qg.QGraphicsTextItem, GuiObjectWithAnim):
    """Qt Text Object with Animation Properties"""
    def __init__(self, text, color, z_stack):
        qg.QGraphicsTextItem.__init__(self, text)
        GuiObjectWithAnim.__init__(self, parent_obj=self)
        self.setDefaultTextColor(color)
        self.setZValue(z_stack)


class GuiLineWithAnim(qg.QGraphicsLineItem, GuiObjectWithAnim):
    """Qt Line Object with Animation Properties"""
    def __init__(self, dimensions, color, z_stack):
        qg.QGraphicsLineItem.__init__(self, *dimensions)  # @dimensions: x, y, w, h
        GuiObjectWithAnim.__init__(self, parent_obj=self)
        self.setPen(color)
        self.setZValue(z_stack)


# Custom Entry Types
class GuiEntryWithWarning(qg.QLineEdit):
    """A line entry with a triggerable visual warning"""
    def __init__(self, default_text=''):
        super(GuiEntryWithWarning, self).__init__()
        self.visual_warning_stage = 0
        if default_text:
            self.setText(str(default_text))

    def visual_warning(self, times_to_flash=3):
        """Triggers several flashes from white to red, num defined by times_to_flash"""
        if self.visual_warning_stage == times_to_flash:
            self.setStyleSheet(qBgWhite)
            self.visual_warning_stage = 0
            return
        if self.visual_warning_stage % 2 == 0:
            self.setStyleSheet(qBgRed)
        else:
            self.setStyleSheet(qBgWhite)
        self.visual_warning_stage += 1
        qc.QTimer.singleShot(150, lambda t=times_to_flash: self.visual_warning(t))


class GuiIntOnlyEntry(GuiEntryWithWarning):
    """An entry that takes only integers, with options for boundary values and max digits allowed"""
    def __init__(self, max_digits=None, default_text='', minimum=None, maximum=None):
        super(GuiIntOnlyEntry, self).__init__(default_text)
        self.max_digits = max_digits
        self.last_valid_entry = str(default_text)
        self.min = minimum
        self.max = maximum
        self.initialize()

    def initialize(self):
        """Sets up entry conditions and connects signals/slots"""
        if self.max_digits:
            self.setMaxLength(self.max_digits)
        self.textEdited.connect(self.check_text_edit)

    def check_text_edit(self):
        """Checks that entries are valid"""
        # Check if we entered a space before the text
        if self.text().startswith(' '):
            self.setText(self.last_valid_entry)
            self.setCursorPosition(0)
        # Main check
        text = self.text().strip()
        if not text:
            self.last_valid_entry = ''
            pos = 0
        else:
            try:
                # did we input a valid integer?
                int(text)
            except ValueError:
                # if not, we revert to entry before it was invalid
                pos = self.cursorPosition() - 1
            else:
                # if valid integer, we update the last valid data
                self.last_valid_entry = text
                pos = self.cursorPosition()
                # we check if our valid integer is beyond the min/max bounds we set
                if self.min and (int(text) < self.min):
                    self.last_valid_entry = str(self.min)
                elif self.max and (int(text) > self.max):
                    self.last_valid_entry = str(self.max)
        self.setText(self.last_valid_entry)
        self.setCursorPosition(pos)

    def set_min_max_value(self, minimum, maximum):
        """sets the min/max values of the entry"""
        self.min = minimum
        self.max = maximum


class GuiDropdownWithWarning(qg.QComboBox):
    """A line entry with a triggerable visual warning"""
    def __init__(self, default_text=''):
        super(GuiDropdownWithWarning, self).__init__()
        self.visual_warning_stage = 0
        if default_text:
            self.setText(str(default_text))

    def visual_warning(self, times_to_flash=3):
        """Triggers several flashes from white to red, num defined by times_to_flash"""
        if self.visual_warning_stage == times_to_flash:
            self.setStyleSheet(qBgWhite)
            self.visual_warning_stage = 0
            return
        if self.visual_warning_stage % 2 == 0:
            self.setStyleSheet(qBgRed)
        else:
            self.setStyleSheet(qBgWhite)
        self.visual_warning_stage += 1
        qc.QTimer.singleShot(150, lambda t=times_to_flash: self.visual_warning(t))


# Custom Buttons
class GuiFlipBtn(qg.QPushButton):
    """A PushButton with 2 states; single toggle function"""
    def __init__(self, default_msg, flipped_msg, default_color='', flipped_color=''):
        super(GuiFlipBtn, self).__init__(default_msg)
        if default_color:
            self.setStyleSheet(default_color)
        self.state = 'default'
        self.default = default_msg, default_color
        self.flipped = flipped_msg, flipped_color

    def toggle_state(self):
        """Flip the message and color of button"""
        if self.state == 'default':
            self.state = 'flipped'
            self.setText(self.flipped[0])
            self.setStyleSheet(self.flipped[1])
        elif self.state == 'flipped':
            self.state = 'default'
            self.setText(self.default[0])
            self.setStyleSheet(self.default[1])


class GuiMultiStateBtn(qg.QPushButton):
    """A PushButton with multiple states"""
    def __init__(self, default_msg, default_color=None, **states):
        super(GuiMultiStateBtn, self).__init__(default_msg)
        if default_color:
            self.setStyleSheet(default_color)
        self.default = default_msg, default_color
        for state in states:
            setattr(self, state, states[state])

    def toggle_state(self, state):
        """Flip the message and color of button"""
        state = getattr(self, state)
        self.setText(state[0])
        self.setStyleSheet(state[1])
