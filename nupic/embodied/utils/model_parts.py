import torch
import numpy as np


def flatten_dims(x, dim):
    """Flatten dimension dim of x.

    Parameters
    ----------
    x : array
        array to flatten.
    dim : int
        dimension that should be flattened.

    Returns
    -------
    array
        Reshaped array.

    """
    if dim == 0:
        return x.reshape((-1,))
    else:
        return x.reshape((-1,) + x.shape[-dim:])


def unflatten_first_dim(x, sh):
    """Unflatten first dimension of x.

    Parameters
    ----------
    x : array
        array to flatten.
    sh : array
        Original shape of x.

    Returns
    -------
    array
        Reshaped array.

    """
    assert (
        x.shape[0] // sh[0] * sh[0] == x.shape[0]
    )  # whether x.shape[0] is N_integer times of sh[0]
    return x.view((sh[0],) + (x.shape[0] // sh[0],) + x.shape[1:])


class small_convnet(torch.nn.Module):
    """Convolutional neural network with three conv2D layer and one fc layer.

    Parameters
    ----------
    ob_space : Space
        Observation space properties (from env.observation_space).
    nonlinear : torch.nn
        nonlinear activation function to use.
    feat_dim : int
        Number of neurons in the hidden layer of the feature network.
    last_nonlinear : torch.nn or None
        nonlinear activation function to use for the last layer.
    layernormalize : bool
        Whether to normalize the last layer.
    batchnorm : bool
        Whether to normalize batches.
    device: torch.device
        Which device to optimize the model on.

    Attributes
    ----------
    H : int
        Height of the input images.
    W : int
        Width of the input images.
    C : int
        Channels of the input images.
    conv : torch.nn.Sequential
        Convolutional network.
    flatten_dim : int
        Flattened dimensionality.
    fc : torch.nn.Linear
        Fully connected output layer.

    """

    def __init__(
        self,
        ob_space,
        nonlinear,
        feat_dim,
        last_nonlinear,
        layernormalize,
        device,
        batchnorm=False,
    ):
        super(small_convnet, self).__init__()
        self.device = device
        # Get the input shape
        self.H = ob_space.shape[0]
        self.W = ob_space.shape[1]
        self.C = ob_space.shape[2]
        # Attributes of the convolutional layers
        feat_list = [[self.C, 32, 8, (4, 4)], [32, 64, 4, (2, 2)], [64, 64, 3, (1, 1)]]
        self.conv = torch.nn.Sequential().to(device)
        oH = self.H
        oW = self.W
        for idx, f in enumerate(feat_list):
            # Add convolutional layer
            self.conv.add_module(
                "conv_%i" % idx,
                torch.nn.Conv2d(f[0], f[1], kernel_size=f[2], stride=f[3]),
            )
            # Apply nonlinear activation function
            if nonlinear == torch.nn.LeakyReLU:
                print("setting leaky relu slope to 0.2")  # to make it like original
                self.conv.add_module(
                    "nl_%i" % idx, torch.nn.LeakyReLU(negative_slope=0.2)
                )
            else:
                self.conv.add_module("nl_%i" % idx, nonlinear())
            if batchnorm:
                # Normalize batch
                self.conv.add_module("bn_%i" % idx, torch.nn.BatchNorm2d(f[1]))
            # Calculations to get flat output dimensionality of last conv layer
            oH = (oH - f[2]) / f[3][0] + 1
            oW = (oW - f[2]) / f[3][1] + 1
            print("H: " + str(oH) + " W: " + str(oW))

        assert oH == int(oH)  # whether oH is a .0 float ?
        assert oW == int(oW)
        print(self.conv)
        self.flatten_dim = int(oH * oW * feat_list[-1][1])
        # Add fc layer at end for feature output
        # TODO: Here the original implementation uses normc_initializer(1.0) from
        # baselines.common.tf_util -> is this important? It changes feature_var on ax=2
        self.fc = torch.nn.Linear(self.flatten_dim, feat_dim).to(device)

        self.last_nonlinear = last_nonlinear
        self.layernormalize = layernormalize
        # initialize weight with xavier uniform distribution
        self.init_weight()

    def init_weight(self):
        """Initialize wieght of network."""
        for m in self.conv:
            if isinstance(m, torch.nn.Conv2d):
                torch.nn.init.xavier_uniform_(m.weight.data)
                torch.nn.init.constant_(m.bias.data, 0.0)
        torch.nn.init.xavier_uniform_(self.fc.weight.data)
        torch.nn.init.constant_(self.fc.bias.data, 0.0)

    def forward(self, x):
        """Forward pass of x through the network.

        Parameters
        ----------
        x : array
            input (observations).

        Returns
        -------
        array
            Output features of the network.

        """
        # run x through the convolutional layers
        x = self.conv(x)
        # Get flattened version of conv output
        # TODO: check that contiguous.view actually does what its supposed to
        x = x.contiguous().view(
            -1, self.flatten_dim
        )  # dims is calculated manually, 84*84 -> 20*20 -> 9*9 ->7*7
        # run through fully connected layer
        x = self.fc(x)
        if self.last_nonlinear is not None:
            # apply activation function the the last layer
            x = self.last_nonlinear(x)
        if self.layernormalize:
            # normalize the last layer
            x = self.layernorm(x)
        return x

    def layernorm(self, x):
        """Normalize a layer."""
        m = torch.mean(x, -1, keepdim=True).to(self.device)
        v = torch.std(x, -1, keepdim=True).to(self.device)
        return (x - m) / (v + 1e-8)


class small_deconvnet(torch.nn.Module):
    def __init__(self, ob_space, feat_dim, nonlinear, ch, positional_bias, device):
        super(small_deconvnet, self).__init__()
        self.H = ob_space.shape[0]
        self.W = ob_space.shape[1]
        self.C = ob_space.shape[2]

        self.feat_dim = feat_dim
        self.nonlinear = nonlinear
        self.ch = ch
        self.positional_bias = positional_bias
        self.device = device

        self.sh = (64, 8, 8)
        self.fc = torch.nn.Sequential(
            torch.nn.Linear(feat_dim, np.prod(self.sh)), nonlinear()
        ).to(self.device)

        # The last kernel_size is 7 not 8 compare to the origin implementation,
        # to make the output shape be [96, 96]
        feat_list = [
            [self.sh[0], 128, 4, (2, 2), (1, 1)],
            [128, 64, 8, (2, 2), (3, 3)],
            [64, ch, 7, (3, 3), (2, 2)],
        ]
        self.deconv = torch.nn.Sequential().to(self.device)
        for i, f in enumerate(feat_list):
            self.deconv.add_module(
                "deconv_%i" % i,
                torch.nn.ConvTranspose2d(
                    f[0], f[1], kernel_size=f[2], stride=f[3], padding=f[4]
                ),
            )
            if i != len(feat_list) - 1:
                # TODO: Set negative slope like in smallconvnet
                self.deconv.add_module("nl_%i" % i, nonlinear())

        self.bias = (
            torch.nn.Parameter(torch.zeros(self.ch, self.H, self.W), requires_grad=True)
            if self.positional_bias
            else None
        )

        self.init_weight()

    def init_weight(self):
        for m in self.fc:
            if isinstance(m, torch.nn.Linear):
                torch.nn.init.xavier_uniform_(m.weight.data)
                torch.nn.init.constant_(m.bias.data, 0.0)
        for m in self.deconv:
            if isinstance(m, torch.nn.ConvTranspose2d):
                torch.nn.init.xavier_uniform_(m.weight.data)
                torch.nn.init.constant_(m.bias.data, 0.0)

    def forward(self, features):
        x = self.fc(features)
        x = x.view((-1,) + self.sh)
        x = self.deconv(x)
        x = x[:, :, 6:-6, 6:-6]
        assert x.shape[-2:] == (84, 84)
        if self.positional_bias:
            x = x + self.bias
        return x