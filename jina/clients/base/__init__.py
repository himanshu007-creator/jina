"""Module containing the Base Client for Jina."""
import abc
import argparse
import inspect
import os
from abc import ABC
from typing import Callable, Union, Optional, Iterator, AsyncIterator

from ..request import GeneratorSourceType
from ...excepts import BadClientInput, ValidationError
from ...helper import typename, ArgNamespace
from ...logging.logger import JinaLogger
from ...logging.predefined import default_logger
from ...parsers import set_client_cli_parser
from ...types.request import Request, Response

InputType = Union[GeneratorSourceType, Callable[..., GeneratorSourceType]]
CallbackFnType = Optional[Callable[[Response], None]]


class BaseClient(ABC):
    """A base client for connecting to the Flow Gateway.

    :param args: the Namespace from argparse
    :param kwargs: additional parameters that can be accepted by client parser
    """

    def __init__(self, args: Optional['argparse.Namespace'] = None, **kwargs):
        if args and isinstance(args, argparse.Namespace):
            self.args = args
        else:
            self.args = ArgNamespace.kwargs2namespace(
                kwargs, set_client_cli_parser(), warn_unknown=True
            )
        self.logger = JinaLogger(self.__class__.__name__, **vars(self.args))

        if not self.args.proxy and os.name != 'nt':
            # (Han 2020 12.12): gRPC channel is over HTTP2 and it does not work when we have proxy
            # as many enterprise users are behind proxy, a quick way to
            # surpass it is by temporally unset proxy. Please do NOT panic as it will NOT
            # affect users os-level envs.
            os.unsetenv('http_proxy')
            os.unsetenv('https_proxy')
        self._inputs = None

    @staticmethod
    def check_input(inputs: Optional[InputType] = None, **kwargs) -> None:
        """Validate the inputs and print the first request if success.

        :param inputs: the inputs
        :param kwargs: keyword arguments
        """

        if inputs is None:
            # empty inputs is considered as valid
            return

        if hasattr(inputs, '__call__'):
            # it is a function
            inputs = inputs()

        kwargs['data'] = inputs
        kwargs['exec_endpoint'] = '/'

        if inspect.isasyncgenfunction(inputs) or inspect.isasyncgen(inputs):
            raise ValidationError(
                'checking the validity of an async generator is not implemented yet'
            )

        try:
            from ..request import request_generator

            r = next(request_generator(**kwargs))
            if not isinstance(r, Request):
                raise TypeError(f'{typename(r)} is not a valid Request')
        except Exception as ex:
            default_logger.error(f'inputs is not valid!')
            raise BadClientInput from ex

    def _get_requests(
        self, **kwargs
    ) -> Union[Iterator['Request'], AsyncIterator['Request']]:
        """
        Get request in generator.

        :param kwargs: Keyword arguments.
        :return: Iterator of request.
        """
        _kwargs = vars(self.args)
        _kwargs['data'] = self.inputs
        # override by the caller-specific kwargs
        _kwargs.update(kwargs)

        if hasattr(self._inputs, '__len__'):
            self._inputs_length = max(1, len(self._inputs) / _kwargs['request_size'])
        else:
            self._inputs_length = None

        if inspect.isasyncgen(self.inputs):
            from ..request.asyncio import request_generator

            return request_generator(**_kwargs)
        else:
            from ..request import request_generator

            return request_generator(**_kwargs)

    @property
    def inputs(self) -> InputType:
        """
        An iterator of bytes, each element represents a Document's raw content.

        ``inputs`` defined in the protobuf

        :return: inputs
        """
        return self._inputs

    @inputs.setter
    def inputs(self, bytes_gen: InputType) -> None:
        """
        Set the input data.

        :param bytes_gen: input type
        """
        if hasattr(bytes_gen, '__call__'):
            self._inputs = bytes_gen()
        else:
            self._inputs = bytes_gen

    @abc.abstractmethod
    async def _get_results(
        self,
        inputs: InputType,
        on_done: Callable,
        on_error: Callable = None,
        on_always: Callable = None,
        **kwargs,
    ):
        ...

    @property
    def client(self) -> 'BaseClient':
        """Return the client object itself

        :return: the Client object
        """
        return self
