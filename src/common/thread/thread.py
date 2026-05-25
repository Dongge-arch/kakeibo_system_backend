# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from concurrent.futures import ThreadPoolExecutor, Future


class Thread:
    """
    スレッド処理のラッパー
    """

    _executor = ThreadPoolExecutor()

    def __init__(self):
        super().__init__()

    def __del__(self):
        Thread._executor.shutdown(wait=True)

    @staticmethod
    def get_executor():
        """
        ThreadPoolExecutor を返す。
        """
        return Thread._executor

    @staticmethod
    def submit(fn, *args, **kwargs) -> Future:
        """
        Submits a callable to be executed with the given arguments.
        """
        return Thread._executor.submit(fn, *args, **kwargs)

    @staticmethod
    def map(fn, *iterables, timeout=None, chunksize=1):
        """
        map のラッパー
        """
        return Thread._executor.map(fn,
                                    *iterables,
                                    timeout=timeout,
                                    chunksize=chunksize)
