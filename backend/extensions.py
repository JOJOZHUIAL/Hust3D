# -*- coding: utf-8 -*-
"""共享扩展实例。

单独放在一个模块里，避免 app / models / blueprints 之间出现循环导入。
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
