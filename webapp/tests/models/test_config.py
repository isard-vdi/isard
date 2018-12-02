#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
from ...models.config import Config

from ..mocks.rethink import *


class TestConfig:
    """
    This is the class for testing the Config class
    """

    class TestInit:
        """
        This is the class responsible for testing the __init__ function
        """

        @staticmethod
        def test_should_work_as_expected():
            cfg = Config(generated_cfg)

            for k, v in generated_cfg.items():
                assert getattr(cfg, k) == v

        @staticmethod
        def test_empty_config():
            cfg = Config()

            for k, v in empty_cfg.items():
                assert getattr(cfg, k) == v

    class TestGet:
        """
        This class is responsible for testing the get function
        """

        @staticmethod
        def test_should_work_as_expected(create_config):
            cfg = Config()
            cfg.conn = create_config

            cfg.get()

            for k, v in generated_cfg.items():
                assert getattr(cfg, k) == v

        @staticmethod
        def test_config_not_found(create_tables):
            cfg = Config()
            cfg.conn = create_tables

            with pytest.raises(Config.NotFound):
                cfg.get()
