r"""Gradient Magnitude Similarity Deviation (GMSD)

This module implements the GMSD in PyTorch.

References:
    [1] Gradient Magnitude Similarity Deviation:
    An Highly Efficient Perceptual Image Quality Index
    (Xue et al., 2013)
    https://arxiv.org/abs/1308.3052
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from piqa.utils import build_reduce, prewitt_kernel, filter2d, tensor_norm

_L_WEIGHTS = torch.FloatTensor([0.299, 0.587, 0.114])


def _gmsd(
    x: torch.Tensor,
    y: torch.Tensor,
    kernel: torch.Tensor,
    value_range: float = 1.,
    c: float = 0.00261,  # 170. / (255. ** 2)
) -> torch.Tensor:
    r"""Returns the GMSD between `x` and `y`,
    without downsampling and color space conversion.

    `_gmsd` is an auxiliary function for `gmsd` and `GMSD`.

    Args:
        x: An input tensor, (N, 1, H, W).
        y: A target tensor, (N, 1, H, W).
        kernel: A 2D gradient kernel, (2, 1, K, K).
        value_range: The value range of the inputs (usually 1. or 255).

        For the remaining arguments, refer to [1].

    Example:
        >>> x = torch.rand(5, 1, 256, 256)
        >>> y = torch.rand(5, 1, 256, 256)
        >>> kernel = torch.rand(2, 1, 3, 3)
        >>> l = _gmsd(x, y, kernel)
        >>> l.size()
        torch.Size([5])
    """

    c *= value_range ** 2

    # Gradient magnitude
    pad = kernel.size(-1) // 2

    gm_x = tensor_norm(filter2d(x, kernel, padding=pad), dim=1)
    gm_y = tensor_norm(filter2d(y, kernel, padding=pad), dim=1)

    # Gradient magnitude similarity
    gms = (2. * gm_x * gm_y + c) / (gm_x ** 2 + gm_y ** 2 + c)

    # Gradient magnitude similarity diviation
    gmsd = (gms - gms.mean((-1, -2), keepdim=True)) ** 2
    gmsd = torch.sqrt(gmsd.mean((-1, -2)))

    return gmsd


def gmsd(
    x: torch.Tensor,
    y: torch.Tensor,
    kernel: torch.Tensor = None,
    **kwargs,
) -> torch.Tensor:
    r"""Returns the GMSD between `x` and `y`.

    Args:
        x: An input tensor, (N, 3, H, W).
        y: A target tensor, (N, 3, H, W).
        kernel: A 2D gradient kernel, (2, 1, K, K).
            If `None`, use the Prewitt kernel instead.

        `**kwargs` are transmitted to `_gmsd`.

    Example:
        >>> x = torch.rand(5, 3, 256, 256)
        >>> y = torch.rand(5, 3, 256, 256)
        >>> l = gmsd(x, y)
        >>> l.size()
        torch.Size([5])
    """

    # Downsample
    x = F.avg_pool2d(x, kernel_size=2, ceil_mode=True)
    y = F.avg_pool2d(y, kernel_size=2, ceil_mode=True)

    # RGB to luminance
    l_weights = _L_WEIGHTS.to(x.device).view(1, 3, 1, 1)

    x = F.conv2d(x, l_weights)
    y = F.conv2d(y, l_weights)

    # Kernel
    if kernel is None:
        kernel = prewitt_kernel()
        kernel = torch.stack([kernel, kernel.t()]).unsqueeze(1)
        kernel = kernel.to(x.device)

    return _gmsd(x, y, kernel, **kwargs)


class GMSD(nn.Module):
    r"""Creates a criterion that measures the GMSD
    between an input and a target.

    Args:
        kernel: A 2D gradient kernel, (2, 1, K, K).
            If `None`, use the Prewitt kernel instead.
        reduction: Specifies the reduction to apply to the output:
            `'none'` | `'mean'` | `'sum'`.

        `**kwargs` are transmitted to `_gmsd`.

    Shape:
        * Input: (N, 3, H, W)
        * Target: (N, 3, H, W)
        * Output: (N,) or (1,) depending on `reduction`

    Example:
        >>> criterion = GMSD().cuda()
        >>> x = torch.rand(5, 3, 256, 256).cuda()
        >>> y = torch.rand(5, 3, 256, 256).cuda()
        >>> l = criterion(x, y)
        >>> l.size()
        torch.Size([])
    """

    def __init__(
        self,
        kernel: torch.Tensor = None,
        reduction: str = 'mean',
        **kwargs,
    ):
        r""""""
        super().__init__()

        if kernel is None:
            kernel = prewitt_kernel()
            kernel = torch.stack([kernel, kernel.t()]).unsqueeze(1)

        self.register_buffer('kernel', kernel)
        self.register_buffer('l_weights', _L_WEIGHTS.view(1, 3, 1, 1))

        self.reduce = build_reduce(reduction)
        self.kwargs = kwargs

    def forward(
        self,
        input: torch.Tensor,
        target: torch.Tensor,
    ) -> torch.Tensor:
        r"""Defines the computation performed at every call.
        """

        # Downsample
        input = F.avg_pool2d(input, 2, ceil_mode=True)
        target = F.avg_pool2d(target, 2, ceil_mode=True)

        # RGB to luminance
        input = F.conv2d(input, self.l_weights)
        target = F.conv2d(target, self.l_weights)

        # GMSD
        l = _gmsd(input, target, self.kernel, **self.kwargs)

        return self.reduce(l)
