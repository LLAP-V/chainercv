from __future__ import division

import numpy as np

import chainer
import chainer.functions as F


def _elementwise_softmax_cross_entropy(x, t):
    assert x.shape[:-1] == t.shape
    shape = t.shape
    x = F.reshape(x, (-1, x.shape[-1]))
    t = F.flatten(t)
    return F.reshape(
        F.softmax_cross_entropy(x, t, reduce='no'), shape)


def _hard_negative(x, positive, k):
    xp = chainer.cuda.get_array_module(x, positive)
    x = chainer.cuda.to_cpu(x)
    positive = chainer.cuda.to_cpu(positive)
    rank = (x * (positive - 1)).argsort(axis=1).argsort(axis=1)
    hard_negative = rank < (positive.sum(axis=1) * k)[:, np.newaxis]
    return xp.array(hard_negative)


def multibox_loss(x_loc, x_conf, t_loc, t_conf, k):
    """Computes multibox losses

    This is a loss function used in [#]_.

    .. [#] Wei Liu, Dragomir Anguelov, Dumitru Erhan,
       Christian Szegedy, Scott Reed, Cheng-Yang Fu, Alexander C. Berg.
       SSD: Single Shot MultiBox Detector. ECCV 2016.

    Args:
        x_loc (chainer.Variable): A variable which indicates predicted
            locations of bounding boxes. Its shape is :math:`(B, K, 4)`,
            where :math:`B` is the number of samples in the batch and
            :math:`K` is the number of default bounding boxes.
        x_conf (chainer.Variable): A variable which indicates predicted
            classes of bounding boxes. Its shape is :math:`(B, K, n\_class)`.
            This function assumes the first class is background (negative).
        t_loc (chainer.Variable): A variable which indicates ground truth
            locations of bounding boxes. Its shape is :math:`(B, K, 4)`.
        t_conf (chainer.Variable): A variable which indicates ground truth
            classes of bounding boxes. Its shape is :math:`(B, K)`.
        k (float): A coefficient which is used to hard negative mining.
            This value determines the ratio between the number of positives
            and that of mined negatives. The value used in the original paper
            is :obj:`3`.

    Returns:
        tuple of chainer.Variable:
        This function returns two :obj:`chainer.Variable`: :obj:`loc_loss` and
        :obj:`conf_loss`.
    """
    xp = chainer.cuda.get_array_module(t_conf.data)

    positive = t_conf.data > 0
    n_positive = positive.sum()
    if n_positive == 0:
        z = chainer.Variable(np.zeros((), dtype=np.float32))
        return z, z

    loc_loss = F.huber_loss(x_loc, t_loc, 1, reduce='no')
    loc_loss = F.sum(loc_loss, axis=2)
    loc_loss *= positive.astype(loc_loss.dtype)
    loc_loss = F.sum(loc_loss) / n_positive

    conf_loss = _elementwise_softmax_cross_entropy(x_conf, t_conf)
    hard_negative = _hard_negative(conf_loss.data, positive, k)
    conf_loss *= xp.logical_or(positive, hard_negative).astype(conf_loss.dtype)
    conf_loss = F.sum(conf_loss) / n_positive

    return loc_loss, conf_loss
