import os
from typing import Optional

import numpy as np

from . import BaseDenseNdArray
from ....proto import jina_pb2

__all__ = ['BaseDenseNdArray']


class DenseNdArray(BaseDenseNdArray):
    """
    Dense NdArray powered by numpy, supports quantization method.

    Most of the cases you don't want use this class directly, use :class:`NdArray` instead.

    :param proto: the protobuf message, when not given then create a new one
    :param dtype: the dtype used when stored as protobuf message.
    :param args: Additional positional arguments which are just used for the parent initialization
    :param kwargs: Additional keyword arguments which are just used for the parent initialization
        Availables are ``fp16``, ``uint8``, default is None.

    .. note::
        Remarks on quantization:
        The quantization only works when ``x`` is in ``float32`` or ``float64``. The motivation is to
        save the network bandwidth by using less bits to store the numpy array in the protobuf.

            - ``fp16`` quantization is lossless, can be used widely. Each float is represented by 16 bits.
            - ``uint8`` quantization is lossy. Each float is represented by 8 bits.
            The algorithm behind is standard scaling.

        the quantize type is stored and the blob is self-contained to recover the original numpy array
    """

    def __init__(
        self,
        proto: Optional['jina_pb2.NdArrayProto'] = None,
        dtype: Optional[str] = None,
        *args,
        **kwargs
    ):
        super().__init__(proto, *args, **kwargs)
        self._dtype = dtype or os.environ.get('JINA_ARRAY_QUANT')

    @property
    def value(self) -> 'np.ndarray':
        """
        Get the value of protobuf and return in :class:`np.ndarray`.

        :return: ndarray value
        """
        blob = self._pb_body
        if blob.buffer:
            x = np.frombuffer(blob.buffer, dtype=blob.dtype)

            if blob.quantization == jina_pb2.DenseNdArrayProto.FP16:
                x = x.astype(blob.original_dtype)
            elif blob.quantization == jina_pb2.DenseNdArrayProto.UINT8:
                x = x.astype(blob.original_dtype) * blob.scale + blob.min_val

            return x.reshape(blob.shape)
        elif len(blob.shape) > 0:
            return np.zeros(blob.shape)

    @value.setter
    def value(self, value: 'np.ndarray'):
        """
        Set the value of protobuf with :param:`value` :class:`np.ndarray`.

        :param value: set the ndarray
        """
        blob = self._pb_body
        x = value

        if self._dtype == 'fp32' and x.dtype == np.float64:
            blob.quantization = jina_pb2.DenseNdArrayProto.FP32
            blob.original_dtype = x.dtype.name
            x = x.astype(np.float32)
        elif self._dtype == 'fp16' and (x.dtype == np.float32 or x.dtype == np.float64):
            blob.quantization = jina_pb2.DenseNdArrayProto.FP16
            blob.original_dtype = x.dtype.name
            x = x.astype(np.float16)
        elif self._dtype == 'uint8' and (
            x.dtype == np.float32 or x.dtype == np.float64 or x.dtype == np.float16
        ):
            blob.quantization = jina_pb2.DenseNdArrayProto.UINT8
            blob.max_val, blob.min_val = x.max(), x.min()
            blob.original_dtype = x.dtype.name
            blob.scale = (blob.max_val - blob.min_val) / 256
            x = ((x - blob.min_val) / blob.scale).astype(np.uint8)
        else:
            blob.quantization = jina_pb2.DenseNdArrayProto.NONE

        blob.buffer = x.tobytes()
        blob.ClearField('shape')
        blob.shape.extend(list(x.shape))
        blob.dtype = x.dtype.str
