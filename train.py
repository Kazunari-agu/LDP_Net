#coding: 'utf-8'

"""
LDP_Net
train

created by Kazunari on 2018/08/23 
"""

from __future__ import division

import matplotlib
matplotlib.use("Agg")

import argparse
import sys
sys.path.append(".")
import numpy as np
import os.path as osp
import datetime

import matplotlib

import chainer

chainer.set_debug(True)

from chainer.datasets import TransformDataset
from chainer import training
from chainer.training import extensions

from model.ldp_net import LDP_Net
from model.ldp_net_train_chain import LDPNetTrainChain

from dataset.Local_Depth_Dataset import LocalDepthDataset
from dataset.LDD_Transform import LDDTransform

def main():
    parser = argparse.ArgumentParser(
        description="Training script for LDP Net"
    )
    parser.add_argument('--dataset_path', '-p', type=str,
                        default="/Users/Kazunari/projects/datasets/LocalDepthDataset")
    parser.add_argument('--gpu', '-g', type=int, default=-1)
    parser.add_argument('--multi_gpu', '-m', action="store_true")
    parser.add_argument('--lr', '-l', type=float, default=1e-3)
    parser.add_argument('--batch_size', '-b', type=int, default=16)
    parser.add_argument('--out', '-o', default='train_result',
                        help='Root directory of output')
    parser.add_argument('--dir', '-d', default=None,
                        help='Output directory')
    parser.add_argument('--seed', '-s', type=int, default=0)
    parser.add_argument('--step_size', '-ss', type=int, default=50000)
    parser.add_argument('--iteration', '-i', type=int, default=50000)
    args = parser.parse_args()

    np.random.seed(args.seed)

    if args.out is not "train_result":
        out_dir = args.out
    elif args.out is "train_result" and args.dir is not None:
        out_dir = osp.join(args.out, args.dir)
    else:
        import datetime
        out_dir = osp.join(args.out, "{0:%Y%m%d_%H%M%S}".format(datetime.datetime.now()))

    train_data = LocalDepthDataset(args.dataset_path, mode="train")
    test_data = LocalDepthDataset(args.dataset_path, mode="test")

    rgbd_channel = 4
    n_class = train_data.get_class_id_size()

    ldp_net = LDP_Net(f_size=64, rgbd_channel=rgbd_channel, n_class=n_class)

    model = LDPNetTrainChain(ldp_net)

    if args.multi_gpu:
        import chainermn

        # Setting for Multi GPU Training
        comm = chainermn.create_communicator('hierarchical')
        device = comm.intra_rank

        n_node = comm.intra_rank
        n_gpu = comm.size
        chainer.cuda.get_device_from_id(device).use()

        total_batch_size = n_gpu * args.batch_size

        args.lr = args.lr * total_batch_size

        optimizer = chainermn.create_multi_node_optimizer(chainer.optimizers.MomentumSGD(lr=args.lr, momentum=0.9), comm)
    elif args.gpu >= 0:
        chainer.cuda.get_device_from_id(args.gpu).use()
        model.to_gpu()

        optimizer = chainer.optimizers.MomentumSGD(lr=args.lr, momentum=0.9)
    else:
        optimizer = chainer.optimizers.MomentumSGD(lr=args.lr, momentum=0.9)


    optimizer.setup(model)
    # TODO : Confirm that add_hook is needed.
    optimizer.add_hook(chainer.optimizer.optimizer_hooks.WeightDecay(rate=0.0005))

    train_data = TransformDataset(train_data, LDDTransform(train_data))

    if args.multi_gpu:
        if comm.rank != 0:
            train_data = None
            test_data = None
        train_data = chainermn.scatter_dataset(train_data, comm, shuffle=True)

    train_iter = chainer.iterators.SerialIterator(train_data, args.batch_size)

    updater = chainer.training.updaters.StandardUpdater(
        train_iter, optimizer, device=args.gpu)

    trainer = training.Trainer(updater, (args.iteration, 'iteration'), out=out_dir)

    trainer.extend(
        extensions.snapshot_object(model.ldp_net, 'snapshot_model.npz'),
        trigger=(2000, "iteration"))

    log_interval = 25, 'iteration'
    print_interval = 25, 'iteration'

    trainer.extend(extensions.LogReport(trigger=log_interval))
    trainer.extend(extensions.observe_lr(), trigger=log_interval)
    trainer.extend(extensions.PrintReport(
        ['iteration', 'epoch', 'elapsed_time', 'lr', 'main/loss']),
        trigger=print_interval)
    trainer.extend(extensions.ProgressBar(update_interval=10))

    trainer.run()

if __name__ == '__main__':
    main()
