# coding: 'utf-8'

"""
LDP_Net
LDD_Transform
created by Kazunari on 2018/08/23
"""

import cv2
import sys
import numpy as np

sys.path.append(".")

class LDDTransform(object):
    def __init__(self, localDepthDataset, normalize=False):
        self.mean_color = localDepthDataset.mean_color
        self.image_mean = localDepthDataset.image_mean
        self.image_stddev = localDepthDataset.image_stddev
        self.image_size = localDepthDataset.image_size
        self.down_sampling_size = localDepthDataset.down_sampling_size

        self.input_roi_size = (64, 64)
        self.class_id_size = localDepthDataset.get_class_id_size()
        self.normalize = normalize

    """ Resize Image and Label Depth ( Original Size -> NYU Dataset Size (640 x 480) ) """
    def get_resized_data(self, img, depth, roi):
        """ Resize data to Image size(640 x 480) """
        resized_img = cv2.resize(img, (self.image_size[1], self.image_size[0]), interpolation=cv2.INTER_LINEAR)
        resized_dpt = cv2.resize(depth, self.image_size, interpolation=cv2.INTER_NEAREST)

        original_size = img.shape[:2]
        size_diff_ratio = (self.image_size[1] / original_size[1],
                           self.image_size[0] / original_size[0])

        resized_roi = np.asarray([roi[0] * size_diff_ratio[0],
                                  roi[1] * size_diff_ratio[1],
                                  roi[2] * size_diff_ratio[0],
                                  roi[3] * size_diff_ratio[1]], dtype=np.float32)

        """ DownSampling resized data to resize to scale 1/2 """
        ds_img = cv2.resize(resized_img,
                            (self.down_sampling_size[1], self.down_sampling_size[0]),
                            interpolation=cv2.INTER_LINEAR)
        ds_dpt = cv2.resize(resized_dpt,
                            (self.down_sampling_size[1], self.down_sampling_size[0]),
                            interpolation=cv2.INTER_NEAREST)

        ds_roi = resized_roi / 2

        return ds_img, ds_dpt, ds_roi

    def get_roi_data(self, img, depth, pred_depth, roi):
        roi = np.asarray(np.floor(roi), dtype=np.int)

        dst_img = img[roi[1]:roi[3], roi[0]:roi[2]]
        dst_dpt = depth[roi[1]:roi[3], roi[0]:roi[2]]
        dst_pred_dpt = pred_depth[roi[1]:roi[3], roi[0]:roi[2]]

        return dst_img, dst_dpt, dst_pred_dpt

    def get_cropped_roi_data(self, img, depth, pred_depth, roi):
        # Convert roi (u, v, w, h) -> local_region ( u1, v1, u2, v2 )
        roi_with_point = [roi[0], roi[1],
                          roi[0] + roi[2], roi[1] + roi[3]]

        resized_img, resized_depth, resized_roi = self.get_resized_data(img, depth, roi_with_point)

        roi_img, roi_depth, roi_pred_depth = self.get_roi_data(resized_img, resized_depth, pred_depth, resized_roi)

        return roi_img, roi_depth, roi_pred_depth, resized_roi

    def resize_to_input(self, img, depth, pred_depth):
        dst_img = cv2.resize(img, self.input_roi_size, interpolation=cv2.INTER_LINEAR)
        dst_depth = cv2.resize(depth, self.input_roi_size, interpolation=cv2.INTER_NEAREST)
        dst_pred_depth = cv2.resize(pred_depth, self.input_roi_size, interpolation=cv2.INTER_NEAREST)

        dst_img = np.asarray(dst_img, dtype=np.float32).transpose(2, 0, 1)

        dst_depth = np.asarray(dst_depth, dtype=np.float32)
        dst_depth = np.expand_dims(dst_depth, axis=0)

        dst_pred_depth = np.asarray(dst_pred_depth, dtype=np.float32)
        dst_pred_depth = np.expand_dims(dst_pred_depth, axis=0)

        return dst_img, dst_depth, dst_pred_depth

    def __call__(self, in_data):
        roi, class_id, img, pred_depth, depth = in_data

        roi_img, roi_depth, roi_pred_depth, _ = self.get_cropped_roi_data(img, depth, pred_depth, roi)

        roi_img, roi_depth, roi_pred_depth = self.resize_to_input(roi_img, roi_depth, roi_pred_depth)

        # Subtract mean and standardize using std
        roi_img_std = ((roi_img - self.image_mean) / self.image_stddev)

        # Normalize depth with MinMax Normalization
        if self.normalize:
            roi_depth = (roi_depth - roi_depth.min()) / (roi_depth.max() - roi_depth.min())
            roi_pred_depth = (roi_pred_depth - roi_pred_depth.min()) / (roi_pred_depth.max() - roi_pred_depth.min())

        # Create Mask
        eps = np.finfo(np.float32).eps
        mask = eps <= roi_depth

        class_vector = np.zeros([self.class_id_size, self.input_roi_size[0], self.input_roi_size[1]], dtype=np.float32)
        class_vector[class_id, :, :] = 1

        img = roi_img_std
        c_map = class_vector
        pred_depth = roi_pred_depth
        t = roi_depth
        mask = mask

        return img, pred_depth, c_map, t, mask