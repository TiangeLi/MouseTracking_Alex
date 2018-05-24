# coding=utf-8

"""Handles IO and Configurations across all modules and devices"""

import sys
import numpy as np
from Misc.GlobalVars import *


class MainSettings(object):
    """Holds all relevant user configurable settings"""
    def __init__(self):
        # Last Used Settings
        self.last_save_dir = ''
        self.ttl_time = 0.0
        # target area settings (areas that mouse will receive stimulation if within)
        self.target_area_radius = 30
        self.last_targ_areas = None
        self.target_areas = {}
        self.last_quadrant = BOTTOMLEFT
        self.bounding_coords = DEFAULT_BOUNDS

    def load_examples(self):
        """Example settings for first time users"""
        self.last_save_dir = HOME_DIR + '\\Desktop\\MouseTracking'
        self.ttl_time = 600.0  # in secs; 10 min Default
        self.last_targ_areas = TargetAreas(check_radius=False)


# Target Area Containers and Functions
class TargetAreas(object):
    """A group of target regions"""
    def __init__(self, check_radius, min_sep=1, with_edge=False, dirs=None):
        self.name = None
        self.areas = []
        self.generate_targ_areas(check_radius=check_radius,
                                 min_sep=min_sep,
                                 with_edge=with_edge,
                                 dirs=dirs)

    def generate_targ_areas(self, check_radius, min_sep, with_edge, dirs):
        """Randomly sample num points from a 2D normal"""
        # We sample for num_to_sample points
        areas = []
        num_to_sample = 6
        # If we check for distance conditions, we need to find out how big the containing rect is
        if check_radius:
            x1, y1, x2, y2 = self.get_boundaries(dirs)
            xscale = x2 - x1
            xshift = x1
            yscale = y2 - y1
            yshift = y1
            radius = dirs.settings.target_area_radius
            min_sep = radius * min_sep
        # Generate points until we have num_to_sample points
        while len(areas) < num_to_sample:
            # If we don't check for distance conditions, we generate and append to list
            loc = np.random.multivariate_normal((0.5, 0.5), (((0.5/3)**2, 0), (0, (0.5/3)**2)), size=1)[0]
            use = True
            # If we do check for distance,
            # we make sure distance between new point and all other points > min_sep
            # and also distance to edge is radius if with_edge
            if check_radius:
                x = int((loc[0] * xscale) + xshift)
                y = int((loc[1] * yscale) + yshift)
                # check that distance to edge is > radius
                if with_edge:
                    if not self.pt_in_bounds(x, y, x1, y1, x2, y2, radius):
                        continue
                # check that distance between points is > min_sep
                for area in areas:
                    cx = int((area.x * xscale) + xshift)
                    cy = int((area.y * yscale) + yshift)
                    if ((x-cx)**2 + (y-cy)**2) <= min_sep ** 2:
                        use = False
            if use:
                if 0 <= loc[0] <= 1 and 0 <= loc[1] <= 1:
                    areas.append(SingleTargetArea(x=loc[0], y=loc[1], area_id=len(areas)))
        self.areas = areas

    @staticmethod
    def get_boundaries(dirs):
        """Gets boundaries in which to generate and confine new coordinates"""
        x1, y1 = dirs.settings.bounding_coords[0]
        x2, y2 = dirs.settings.bounding_coords[1]
        xmid = (x1 + x2) / 2
        ymid = (y1 + y2) / 2
        quadrant_selector = {
            TOPLEFT: (x1, y1, xmid, ymid),
            TOPRIGHT: (xmid, y1, x2, ymid),
            BOTTOMLEFT: (x1, ymid, xmid, y2),
            BOTTOMRIGHT: (xmid, ymid, x2, y2),
        }
        return quadrant_selector[dirs.settings.last_quadrant]

    @staticmethod
    def pt_in_bounds(x, y, x1, y1, x2, y2, distance):
        """Checks that (x, y) is distance away from all walls of rect defined by x1y1x2y2"""
        x1 = x1 + distance
        x2 = x2 - distance
        y1 = y1 + distance
        y2 = y2 - distance
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
        else:
            return False


class SingleTargetArea(object):
    """A single target region"""
    def __init__(self, x, y, area_id=None, tested=False):
        self.x = x
        self.y = y
        self.area_id = area_id
        self.tested = tested
