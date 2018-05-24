# coding=utf-8

"""Simplifies the way images are sent between processes"""

import numpy as np
import multiprocessing as mp
import PyQt4.QtGui as qg
import PyQt4.QtCore as qc


class SyncableMPArray(object):
    """Sharable MP Array with Built in Sync Event"""
    def __init__(self, dims):
        self.array = mp.Array('B', int(np.prod(dims)), lock=mp.Lock())
        self.array_dims = dims
        self.sync_event = mp.Event()
        self.sync_event.clear()

    def generate_np_array(self):
        """Create an NP Array referencing self.mp_array"""
        return SyncableNPArray(self)


class SyncableNPArray(np.ndarray):
    """Numpy array that references supplied mp_array"""
    def __new__(cls, mp_array):
        array = np.frombuffer(mp_array.array.get_obj(), dtype='uint8').reshape(mp_array.array_dims).view(cls)
        array.array_dims = mp_array.array_dims
        array.sync_event = mp_array.sync_event
        return array

    def __array_finalize__(self, array):
        self.array_dims = getattr(array, 'array_dims', None)
        self.sync_event = getattr(array, 'sync_event', None)

    def send_img(self, data):
        """Sends an image to the mp array"""
        self[:] = data

    def can_send_img(self):
        """Report if receiving party is ready for new frame"""
        return not self.sync_event.is_set()

    def set_can_send_img(self):
        """Set ready to receive to True"""
        self.sync_event.clear()

    def can_recv_img(self):
        """report if image has been sent by sending party"""
        return self.sync_event.is_set()

    def set_can_recv_img(self):
        """set img sent to True"""
        self.sync_event.set()


class PixmapWithArray(qg.QGraphicsPixmapItem):
    """QPixmap that displays images from supplied mp_array. Needs to be updated using external timer"""
    def __init__(self, scene, mp_array):
        super(PixmapWithArray, self).__init__(scene=scene)
        self.mp_array = mp_array
        self.np_array = self.mp_array.generate_np_array()

    def update_display(self):
        """Update pixmap to display next frame in mp_array"""
        if self.np_array.can_recv_img():
            img = qg.QImage(self.np_array.data, self.np_array.shape[1], self.np_array.shape[0], qg.QImage.Format_RGB888)
            self.setPixmap(qg.QPixmap.fromImage(img))
            self.np_array.set_can_send_img()


class LabelWithArray(qg.QLabel):
    """QLabel displaying images from supplied array. Less complicated to use, less flexibility. Has own timer"""
    def __init__(self, mp_array, update_interval_ms, size=None):
        super(LabelWithArray, self).__init__()
        self.mp_array = mp_array
        self.np_array = self.mp_array.generate_np_array()
        # set own size to fit array
        if not size:
            size = mp_array.array_dims[1], mp_array.array_dims[0]
        self.setMinimumSize(*size)
        self.setMaximumSize(*size)
        # start timer to update display
        timer = qc.QTimer(self)
        timer.timeout.connect(self.update_display)
        timer.start(update_interval_ms)

    def update_display(self):
        """Update label to display next frame in mp_array"""
        if self.np_array.can_recv_img():
            img = qg.QImage(self.np_array.data, self.np_array.shape[1], self.np_array.shape[0], qg.QImage.Format_RGB888)
            self.setPixmap(qg.QPixmap.fromImage(img))
            self.np_array.set_can_send_img()
