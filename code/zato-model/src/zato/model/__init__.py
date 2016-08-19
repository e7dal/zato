# -*- coding: utf-8 -*-

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from contextlib import closing
from datetime import datetime
from inspect import isclass
from uuid import uuid4
import warnings

# SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm.session import sessionmaker

# Zato
from zato.common import invalid as _invalid
from zato.model.data_type import DataType, DateTime, NetAddress, Text
from zato.model.sql import Group, GroupTag, Item, ItemTag, SubGroup, SubGroupTag, Tag

warnings.filterwarnings('ignore',
                        r'^Dialect sqlite\+pysqlite does \*not\* support Decimal objects natively\, '
                        'and SQLAlchemy must convert from floating point - rounding errors and other '
                        'issues may occur\. Please consider storing Decimal numbers as strings or '
                        'integers on this platform for lossless storage\.$',
                        SAWarning, r'^sqlalchemy\.sql\.type_api$')

# ################################################################################################################################

instance_name_template = 'user.model.instance.{}'

# ################################################################################################################################

_item_by_id_attrs=(Item.id,)
_item_all_attrs=(Item.id, Item.object_id, Item.name, Item.version, Item.last_updated_ts, Item.is_active, Item.is_internal)

# ################################################################################################################################

class Model(object):
    model_name = _invalid

    # Computed once in get_name
    _model_name = None

    # ModelManager instance
    manager = None

    def __init__(self, tags=None):

        # User-facing one
        self.id = None

        # Internal, SQL-based one
        self._id = None

        self._name = ''
        self.version = 0
        self.last_updated_ts = None
        self.is_active = True
        self.is_internal = False

        self.tags = tags or []

        #
        # Maps attributes that can be set by users to instances of DataType.
        # We do it here in __init__.py so that users are able to overwrite the attributes by mere assignment.
        # For instance, if we have a class such as ..
        #
        # class Bank(DataType):
        #   branch_name = Text()
        #
        # .. then branch_name will go to self.attrs and users are able to simply assign values to Python objects:
        #
        # bank = Bank()
        # bank.branch_name = 'My Street 123'
        #
        self.attrs = {}

        for name in dir(self):
            attr = getattr(self, name)
            if isinstance(attr, DataType):
                self.attrs[name] = attr

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

    @classmethod
    def get_name(class_):
        if not class_._model_name:
            class_._model_name = class_.model_name if class_.model_name != _invalid else class_.__name__.lower()

        return class_._model_name

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

    def save(self, session=None):
        model_name = self.get_name()

        # No ID = the instance surely doesn't exist in database
        if not self.id:

            with closing(self.manager.session()) as session:

                # Add parent instance first
                instance = Item()
                instance.object_id = '{}.{}'.format(model_name, uuid4().hex)
                instance.name = instance_name_template.format(model_name)
                instance.version = 1
                instance.group_id = self.manager.user_models_group_id
                instance.sub_group_id = self.manager.user_models_sub_groups[model_name]

                session.add(instance)
                session.flush()

                for attr_name, attr_type in self.attrs.iteritems():
                    model_value = getattr(self, attr_name)

                    # If model_value is still an instance of DataType it means that user never overwrote it
                    has_value = not isinstance(model_value, DataType)

                    if has_value:
                        value = Item()
                        value.object_id = uuid4().hex
                        value.name = attr_name
                        value.group_id = self.manager.user_models_group_id
                        value.sub_group_id = self.manager.user_models_sub_groups[model_name]
                        value.parent_id = instance.id
                        setattr(value, 'value_{}'.format(attr_type.impl_type), model_value)

                        session.add(value)

                # Commit everything
                session.commit()

                # Note that external users receive object_id as self.id and id goes to self._id
                # This is in order to prevent any ID guessing, e.g. the database may be required
                # to offer strict isolation of data on multiple levels and this is one of them.
                # This becomes important if we take into account the fact that self.id is the one
                # that can be automatically serialized to external data formats, such as JSON or XML.
                self.id = instance.object_id
                self._id = instance.id

        # Else - it may potentially exist, or perhaps its ID is invalid

    @classmethod
    def get(class_, id=None, session=None, *args, **kwargs):
        return class_.manager.get_by_object_id(session, class_, id)

# ################################################################################################################################

class List(object):
    def __init__(self, model):
        self.model = model

# ################################################################################################################################

class Ref(object):
    def __init__(self, model):
        self.model = model

# ################################################################################################################################

class ModelManager(object):

    def __init__(self, sql_echo=False):
        db_path = '/home/dsuch/tmp/zzz.db'
        db_url = 'sqlite:///{}'.format(db_path)
        engine = create_engine(db_url, echo=sql_echo)

        self.session = sessionmaker()
        self.session.configure(bind=engine)

        self.user_models_group_name = 'user.models'
        self.user_models_group_id = None
        self.user_models_sub_groups = {} # Group name -> group ID

        self.set_up_user_models_group()

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

    def set_up_user_models_group(self):

        with closing(self.session()) as session:
            g = session.query(Group).\
                filter(Group.name==self.user_models_group_name).\
                first()

            if not g:
                g = Group()
                g.name = self.user_models_group_name

                session.add(g)
                session.commit()

            self.user_models_group_id = g.id

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

    def add_sub_group(self, sub_group_name):

        with closing(self.session()) as session:

            sg = session.query(SubGroup).\
                filter(SubGroup.name==sub_group_name).\
                filter(SubGroup.group_id==Group.id).\
                filter(Group.name==self.user_models_group_name).\
                first()

            if not sg:
                sg = SubGroup()
                sg.name = sub_group_name
                sg.group_id = session.query(Group.id).filter(Group.name==self.user_models_group_name).one()[0]

                session.add(sg)
                session.commit()

            self.user_models_sub_groups[sub_group_name] = sg.id

            return sg

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

    def register(self, model_class):
        self.add_sub_group(model_class.get_name())
        model_class.manager = self

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

    def get_by_object_id(self, session, class_, object_id):
        """ Returns an instance of an object by its externally visible ID (object_id).
        """
        needs_new_session = not bool(session)

        try:
            _session = self.session() if needs_new_session else session

            model_name = class_.get_name()

            db_instance = _session.query(*_item_all_attrs).\
                filter(Item.object_id==object_id).\
                one()

            db_attrs = _session.query(
                Item.id,
                Item.name,
                Item.object_id,
                Item.value_text).\
                filter(Item.parent_id==db_instance.id).\
                all()

            instance = class_()
            instance.id = db_instance.object_id
            instance._id = db_instance.id
            instance._name = db_instance.name
            instance.version = db_instance.version
            instance.last_updated_ts = db_instance.last_updated_ts
            instance.is_active = db_instance.is_active
            instance.is_internal = db_instance.is_internal

            for db_attr in db_attrs:
                id, name, object_id, value_text = db_attr
                setattr(instance, name, value_text)

            return instance

        finally:
            if needs_new_session:
                _session.close()

# ################################################################################################################################


class Location(Model):
    facility = Ref('Facility')
    site = Ref('Site')
    city = Ref('City')
    state = Ref('State')
    country = Ref('Country')
    region = Ref('Region')

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Facility(Model):
    name = Text()

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Site(Model):
    name = Text()
    address = Text()
    facilities = List(Facility)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class City(Model):
    name = Text()
    sites = List(Site)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class State(Model):
    name = Text()
    cities = List(City)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Country(Model):
    name = Text()
    code = Text()
    states = List(State)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Region(Model):
    name = Text()
    countries = List(Country)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class User(Model):
    name = Text()

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Reader(Model):
    ruid = Text()
    location = Ref(Location)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Application(Model):
    name = Text()
    location = Ref(Location)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Account(Model):
    name = Text()
    users = List(User)
    readers = List(Reader)

# ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 

class Customer(Model):
    name = Text()
    accounts = List(Account)

# ################################################################################################################################

if __name__ == '__main__':

    mgr = ModelManager()

    #mgr.register(Facility)
    #mgr.register(Site)
    #mgr.register(City)
    #mgr.register(State)
    #mgr.register(Country)
    mgr.register(Region)
    #mgr.register(User)
    #mgr.register(Reader)
    #mgr.register(Application)
    #mgr.register(Account)
    #mgr.register(Customer)
    #mgr.register(Location)

    region = Region()
    region.name = 'Asia'
    #region.save()

    print(11, region.id)

    region_id = 'region.30c52df80a434d5fb96d1d465e139bb9'

    region2 = Region.get(region_id)

    print(22, region2.id)
    print(22, repr(region2.name))
    print(22, repr(region2._name))