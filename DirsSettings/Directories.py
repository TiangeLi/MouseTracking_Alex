# coding=utf-8

"""Handles IO, Saving User Configs, and Saving acquired data"""

import pickle
from DirsSettings.Settings import MainSettings
from Misc.CustomFunctions import format_daytime
from Misc.GlobalVars import *


class Directories(object):
    """Controls all Directories and IO operations"""
    def __init__(self):
        # File saving
        self.settings = MainSettings()  # We'll shortly load from file instead (unless this is first time running)
        self.settings_file = HOME_DIR + '\\MouseTrackSettings.stg'
        # Options
        self.made_date_stamped_dir = False
        self.save_on_exit = True
        self.del_all = False  # debug only. DO NOT CHANGE TO TRUE; WILL DELETE ALL SAVED SETTINGS
        # Setup
        self.initialize()

    def initialize(self):
        """Check for files and directories; create new if not exist"""
        if not os.path.isfile(self.settings_file):
            # Load example configs for first time users/after a settings purge
            self.settings.load_examples()
            self.save()
        # Load from settings file
        self.load()
        # Initialize last target areas
        if self.settings.last_targ_areas.name:
            self.settings.last_targ_areas = self.settings.target_areas[self.settings.last_targ_areas.name]

    def save(self):
        """Pickle save to self.settings_file"""
        with open(self.settings_file, 'wb') as file:
            pickle.dump(self.settings, file)

    def load(self):
        """Load from self.settings_file"""
        with open(self.settings_file, 'rb') as file:
            self.settings = pickle.load(file)

    def check_dirs(self):
        """Check if self.settings.last_save_dir exists. Create if not exist"""
        directory = self.settings.last_save_dir
        # If there is a record of the directory, but the directory doesn't actually exist:
        if directory and not os.path.isdir(directory):
            # We make this directory
            os.makedirs(directory)
            # If we just made a new save directory, obviously no datestamped dirs ex
            self.made_date_stamped_dir = False

    def create_date_stamped_dir(self):
        """Creates a date stamped directory for this session"""
        # We grab the current day stamp
        date_stamp = format_daytime(option=DAY, use_as_save=True)
        # We find all directories withni the main save dir that have the above date stamp
        directories = [d for d in os.listdir(self.settings.last_save_dir)
                       if os.path.isdir('{}\\{}'.format(self.settings.last_save_dir, d))
                       and d.startswith(date_stamp)]
        # For directories with the same date stamp, we assign them a number in ascending order
        if len(directories) > 0:
            num = max([int(d.split('#')[-1]) for d in directories]) + 1
        else:
            num = 0
        self.date_stamped_dir = '{}\\{}_#{}'.format(self.settings.last_save_dir, date_stamp, num)
        os.makedirs(self.date_stamped_dir)
        self.made_date_stamped_dir = True

    def list_file_names(self):
        """Returns a list of files in the current save directory"""
        # if we have not created date stamped dir, obviously no files to list. return empty
        if not self.made_date_stamped_dir:
            return []
        # if we did create the dir, then we can look for files in there
        else:
            # just because we have a record of creating it doesn't mean we didnt accidentally delete it
            try:
                files = os.listdir(self.date_stamped_dir)
            except FileNotFoundError:
                self.made_date_stamped_dir = False
                return []  # dir doesn't actually exist. therefore no files exist
            else:
                # File name format: [FILE_NAME]_date_etc.fmt
                # We list the cleaned up file_name without dates or brackets
                file_names = [file.split('[')[1].split(']')[0] for file in files]
                return file_names

    def nuke_files(self):
        """Use with caution: clears all user configs/setting files. Use for debugging only"""
        os.remove(self.settings_file)
