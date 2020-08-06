import os
import numpy as np
import configparser
import math

from photogrammetry_importer.file_handlers.image_file_handler import ImageFileHandler
from photogrammetry_importer.utility.os_utility import get_subdirs 
from photogrammetry_importer.utility.blender_camera_utility import check_radial_distortion
from photogrammetry_importer.utility.blender_logging_utility import log_report
from photogrammetry_importer.types.camera import Camera
from photogrammetry_importer.types.point import Point

class MVEFileHandler(object):

    def str_to_arr(some_str, target_type):
        return [target_type(x) for x in some_str.split()]

    def readline_as_numbers(input_file, target_type):
        line_str = input_file.readline().rstrip()
        return MVEFileHandler.str_to_arr(line_str, target_type)

    @staticmethod
    def parse_rotation_matrix(input_file):
        row_1 = MVEFileHandler.readline_as_numbers(input_file, target_type=float)
        row_2 = MVEFileHandler.readline_as_numbers(input_file, target_type=float)
        row_3 = MVEFileHandler.readline_as_numbers(input_file, target_type=float)
        return np.asarray([row_1, row_2, row_3], dtype=float)

    @staticmethod
    def parse_synth_out(synth_out_ifp):
        points3D = []

        with open(synth_out_ifp, 'r') as input_file:
            meta_data_line = input_file.readline()
            
            num_cameras, num_points = MVEFileHandler.readline_as_numbers(
                input_file, target_type=int)

            # The camera information provided in the synth_0.out file is incomplete
            # Thus, we use the camera information provided in the view folders

            # Consume the lines corresponding to the (incomplete) camera information
            for cam_idx in range(num_cameras):
                intrinsic_line = MVEFileHandler.readline_as_numbers(
                    input_file, target_type=float)
                rotation_mat = MVEFileHandler.parse_rotation_matrix(input_file)
                camera_translation = np.asarray(MVEFileHandler.readline_as_numbers(
                    input_file, target_type=float))

            for point_idx in range(num_points):
                coord = MVEFileHandler.readline_as_numbers(
                    input_file, target_type=float)
                color = MVEFileHandler.readline_as_numbers(
                    input_file, target_type=int)
                measurement_line = MVEFileHandler.readline_as_numbers(
                    input_file, target_type=int)
                point = Point(
                    coord=coord, color=color, id=point_idx, scalars=[])
                points3D.append(point)

        return points3D

    @staticmethod
    def parse_meta(meta_ifp, width, height, camera_name, op):

        view_specific_dir = os.path.dirname(meta_ifp)
        relative_image_fp = os.path.join(view_specific_dir, 'undistorted.png')
        image_dp = os.path.dirname(view_specific_dir)

        camera = Camera()
        camera.image_fp_type = Camera.IMAGE_FP_TYPE_RELATIVE
        camera.image_dp = image_dp
        camera._relative_fp = relative_image_fp
        camera._absolute_fp = os.path.join(
            image_dp, relative_image_fp)
        camera.width = width
        camera.height = height

        ini_config = configparser.RawConfigParser()
        ini_config.read(meta_ifp)
        focal_length_normalized = float(ini_config.get(
            section='camera', option='focal_length'))
        pixel_aspect = float(ini_config.get(
            section='camera', option='pixel_aspect'))
        if pixel_aspect != 1.0:
            log_report('WARNING','Focal length differs in x and y direction, setting it to the average value.', op)
            focal_length_normalized = (focal_length_normalized + focal_length_normalized * pixel_aspect) / 2
        
        max_extend = max(width, height)
        focal_length = focal_length_normalized * max_extend

        principal_point_str = ini_config.get(
            section='camera', option='principal_point')
        principal_point_list = MVEFileHandler.str_to_arr(
            principal_point_str, target_type=float)
        cx_normalized = principal_point_list[0]
        cy_normalized = principal_point_list[1]
        cx = cx_normalized * width
        cy = cy_normalized * height
           
        calib_mat = Camera.compute_calibration_mat(focal_length, cx, cy)
        camera.set_calibration_mat(calib_mat)

        radial_distortion_str = ini_config.get(
            section='camera', option='radial_distortion')
        radial_distortion_vec = np.asarray(MVEFileHandler.str_to_arr(
            radial_distortion_str, target_type=float))
        check_radial_distortion(radial_distortion_vec, relative_image_fp, op)

        rotation_str = ini_config.get(
            section='camera', option='rotation')
        rotation_mat = np.asarray(MVEFileHandler.str_to_arr(
            rotation_str, target_type=float)).reshape((3,3))

        translation_str = ini_config.get(
            section='camera', option='translation')
        translation_vec = np.asarray(MVEFileHandler.str_to_arr(
            translation_str, target_type=float))

        camera.set_rotation_mat(rotation_mat)
        camera.set_camera_translation_vector_after_rotation(translation_vec)
        return camera

    @staticmethod
    def parse_views(views_idp, default_width, default_height, op):

        cameras = []
        subdirs = get_subdirs(views_idp)
        for subdir in subdirs:
            folder_name = os.path.basename(subdir)
            # folder_name = view_0000.mve
            camera_name = folder_name.split('_')[1].split('.')[0]
            undistorted_img_ifp = os.path.join(subdir, "undistorted.png")
            success, width, height = ImageFileHandler.parse_camera_image_file(
                undistorted_img_ifp, default_width=default_width, default_height=default_height, op=op)
            assert success

            meta_ifp = os.path.join(subdir, "meta.ini")
            camera = MVEFileHandler.parse_meta(meta_ifp, width, height, camera_name, op)

            # TODO
            depth_ifp = os.path.join(subdir, "depth-L0.mvei")

            cameras.append(camera)
        return cameras


    @staticmethod
    def parse_mve_workspace(workspace_idp, default_width, default_height, suppress_distortion_warnings, op):

        log_report('INFO', 'Parse MVE workspace: ...', op)
        log_report('INFO', workspace_idp, op)
        views_idp = os.path.join(workspace_idp, "views")
        synth_ifp = os.path.join(workspace_idp, "synth_0.out")
        cameras = MVEFileHandler.parse_views(
            views_idp, default_width, default_height, op)
        points3D = MVEFileHandler.parse_synth_out(
            synth_ifp)
        log_report('INFO', 'Parse MVE workspace: Done', op)
        return cameras, points3D
